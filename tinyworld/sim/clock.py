"""Asynchronous residents: each person lives on their own clock.

The tick loop makes everyone decide at once from one frozen snapshot, then
resolves the batch. Here each resident has a ``wake`` time. Sleeping or working
a shift sets it hours ahead; a short errand, minutes. The world's clock moves
to whoever wakes next, and everyone due within a short *window* decides
concurrently, each from the world as it is when the window opens.

Decisions are committed one at a time through the single writer. Before a
decision is committed it is checked against the world as it is *now*; if the
world changed under it (the loaf is gone), the person is told "that is no
longer possible: ..." and decides again. That is optimistic concurrency, and it
replaces the conflict grouper for most cases.

Interruptions: something addressed to a person, a loud event they can perceive,
or a memory weighty enough to matter cancels their pending wake and wakes them
now.

Recording. The order in which a window's residents were handled is a recorded
draw; every committed decision and every move of the world's clock is a journal
entry. A replay applies the journal and the recorded model replies and makes no
decisions of its own, so it is identical to the run it replays.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from tinyworld.agents import routine as daily
from tinyworld.agents.agent import Acted
from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy
from tinyworld.core.events import Event, EventDraft, Intent, Verb
from tinyworld.core.state import WorldState
from tinyworld.gm import rules
from tinyworld.gm.perception import perceive
from tinyworld.gm.verbs import DEFAULT_MINUTES
from tinyworld.llm.types import CallContext
from tinyworld.sim import commitments as pledges
from tinyworld.sim.loop import Simulation
from tinyworld.sim.scene import openings
from tinyworld.sim.step import StepResult, apply_intents
from tinyworld.sim.tiers import tier_of

TIER1_EVERY = 180  # minutes between turns for background people who think a little
WAIT_AFTER_REFUSAL = 15
# Nobody re-decides faster than this, unless something reaches them. A conversation
# already plays out inside one decision (sim/scene.py), so a spoken line is not a new turn.
MIN_BEAT = 10
# Someone due to act within this long is not worth waking early.
SOON = 30


# -- the two operations a replay repeats --------------------------------------


async def advance_world(sim: Simulation, minutes: int, tick_seq: int) -> list[Event]:
    """Move the world's clock: queued events fire, people age, promises fall due."""
    session = sim.session
    events = sim.record_birth_dates()
    before = session.state.sim_time
    clock = EventDraft(
        kind="system", actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=minutes)]
    )
    due = sim.scheduler.pending(session.branch_id, due_by=before + timedelta(minutes=minutes))
    opening = session.commit([clock] + [d for _, _, d in due], atomic=False, observe=perceive)
    sim.scheduler.mark_done(session.branch_id, [i[0] for i in due], session.state.seq)
    events += opening.events
    events += await sim.upkeep(before, tick_seq)
    events += sim.settle_commitments()
    observations = [o for batch in opening.observed for o in batch]
    if observations:
        await sim.remember(observations, tick_seq)
    return events


async def settle_intents(
    sim: Simulation, intents: list[Intent], tick_seq: int, causes: dict[str, list[int]] | None = None
) -> tuple[StepResult, list[Event]]:
    """Resolve and commit intents, then run what follows from them: scenes, promotion, memory."""
    session = sim.session
    step = await apply_intents(
        session, sim.gm, intents, CallContext(session.branch_id, tick_seq), causes=causes
    )
    observations = list(step.observations)
    scene_events: list[Event] = []
    if sim.scenes is not None:
        for speaker, listener, line in openings(session.state, step.events, sim.scenes.max_scenes):
            scene = await sim.scenes.run(tick_seq, speaker, listener, line)
            scene_events += scene.events
            observations += scene.observations
    await sim.promote(sim.tiers.involved(session.state, step.events + scene_events))
    await sim.remember(observations, tick_seq)
    step.observations = observations
    return step, scene_events


# -- the live scheduler --------------------------------------------------------


@dataclass
class Decided:
    acted: Acted
    mode: str


class AsyncSimulation:
    def __init__(
        self,
        sim: Simulation,
        entropy: Entropy,
        *,
        window: int = 2,
        max_redecide: int = 2,
    ) -> None:
        self.sim = sim
        self.session = sim.session
        self.entropy = entropy
        self.window = window
        self.max_redecide = max_redecide
        self.wake: dict[str, datetime] = {}
        self._lock: asyncio.Lock | None = None
        self._lock_loop = None
        # Called after the clock moves, with the minutes it moved: chance, petitions, the paper.
        self.on_clock = None
        # People whose decision is being made or committed, and those poked meanwhile.
        self._inflight: set[str] = set()
        self._poked: set[str] = set()
        # People who talked in a scene while their own decision was still on its way.
        self._talked: set[str] = set()
        # People something reached while they were walking: they decide, not walk on.
        self._alerted: set[str] = set()
        self.redecided = 0
        self.windows = 0
        self.committed = 0

    @property
    def _writer(self) -> asyncio.Lock:
        """One writer at a time; made again if the event loop it belonged to has gone."""
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    # -- who is awake -----------------------------------------------------

    def residents(self, state: WorldState) -> list[str]:
        return sorted(
            p.id for p in state.people()
            if p.location and persona_of(p) is not None and tier_of(p) < 2
        )

    def _ensure(self, state: WorldState) -> None:
        ids = set(self.residents(state))
        for gone in [i for i in self.wake if i not in ids]:
            del self.wake[gone]
        for i in sorted(ids):
            self.wake.setdefault(i, state.sim_time)

    def interrupt(self, person: str, now: datetime) -> None:
        """Wake this person now, whatever they were doing."""
        self._alerted.add(person)
        if person in self._inflight:
            # They are mid-decision: whatever they choose, they wake again at once.
            self._poked.add(person)
        elif person in self.wake and self.wake[person] > now:
            self.wake[person] = now

    def _cap_for_promises(self, state: WorldState, person: str, when: datetime) -> datetime:
        """Wake in time to set out for a promise, never after."""
        entity = state.entities.get(person)
        if entity is None:
            return when
        for promise in state.open_commitments(person):
            if promise.by != person or promise.kind != "meet":
                continue
            lead = daily.promise_lead(state, entity, promise)
            if lead is None:
                continue
            leave = promise.due - timedelta(minutes=lead)
            if state.sim_time < leave < when:
                when = leave
        return when

    # -- a person decides ---------------------------------------------------

    def _plan_one(self, state: WorldState, person: str):
        """Mode and routine block for a person, from the world as it is now."""
        entity = state.entities[person]
        if tier_of(entity) == 0:
            return self.sim.mode_of(entity)
        return "deliberate", None

    async def _decide(self, state: WorldState, person: str, mode: str, block, tick_seq: int, note: str = "") -> Decided:
        sim = self.sim
        entity = state.entities[person]
        tier = tier_of(entity)
        from tinyworld.world import walking

        dest = walking.route_of(entity)
        alerted = person in self._alerted
        self._alerted.discard(person)
        if dest and dest in state.entities and not note and not alerted:
            # On the road: walking on needs no decision.
            walk = Intent(
                agent=person, verb=Verb.MOVE, target=dest, args={"continue": True},
                text=f"walk on to {state.entities[dest].name}",
            )
            return Decided(Acted(walk, "walking", True, None), "walk")
        if mode == "routine" and block is not None and not note:
            limit = min(block.minutes_left(state.sim_time), sim.max_jump_minutes)
            intent = daily.routine_intent(state, entity, block, limit)
            if intent is not None:
                return Decided(Acted(intent, "routine", True, None), "routine")
            mode = "react"
        agent = sim.agent if tier == 0 else sim.agent_tier1
        if agent is None:
            return Decided(Acted(Intent(agent=person, verb=Verb.WAIT, text="idle"), "", False, None), "idle")
        hint = daily.hint(state, entity, block)
        if note:
            hint = (hint + "\n" if hint else "") + note
        thinker = sim.mind if (sim.mind is not None and tier == 0 and mode == "deliberate") else agent
        acted = await thinker.act(
            state, entity, self.session.branch_id, CallContext(self.session.branch_id, tick_seq, person),
            sim._last_act_tick(person), hint=hint, recent=sim.recent_actions(person),
            promises=pledges.lines_for(state, person),
        )
        return Decided(acted, mode)

    def _duration(self, outcome, intent: Intent) -> int:
        minutes = getattr(outcome, "minutes", 0) or 0
        if minutes <= 0:
            arg = intent.args.get("minutes")
            minutes = arg if isinstance(arg, int) and not isinstance(arg, bool) and arg > 0 else DEFAULT_MINUTES.get(intent.verb, 10)
        if intent.verb is Verb.MOVE:
            return max(1, int(minutes))
        return max(MIN_BEAT, int(minutes))

    # -- the single writer --------------------------------------------------

    async def _commit(self, person: str, decided: Decided, state_at_start: WorldState, tick_seq: int) -> None:
        tries = 0
        while True:
            async with self._writer:
                current = self.session.state
                verdict = rules.check(current, decided.acted.intent)
                stale = verdict.status == "impossible"
                if not stale or tries >= self.max_redecide:
                    if stale:
                        # Out of patience: do the sensible small thing instead.
                        decided = Decided(
                            Acted(Intent(agent=person, verb=Verb.WAIT, args={"minutes": WAIT_AFTER_REFUSAL},
                                         text="waits, unsure"), "", False, None), "idle")
                    await self._apply(person, decided, tick_seq)
                    return
                reason = verdict.reason
            # The world moved under this decision: decide again, outside the lock.
            tries += 1
            self.redecided += 1
            current = self.session.state
            mode, block = self._plan_one(current, person)
            decided = await self._decide(
                current, person, "react" if mode == "routine" else mode, block, tick_seq,
                note=f"That is no longer possible: {reason}. The situation has changed; decide again.",
            )

    async def _apply(self, person: str, decided: Decided, tick_seq: int) -> None:
        session = self.session
        intent = decided.acted.intent
        causes = {person: decided.acted.causes}
        session.store.journal_add(
            session.branch_id, session.state.seq, "async_intents",
            {"intents": [intent.model_dump(mode="json")], "tick_seq": tick_seq, "causes": causes},
        )
        step, scene_events = await settle_intents(self.sim, [intent], tick_seq, causes)
        self.committed += 1
        state = session.state
        outcome = step.outcomes[0] if step.outcomes else None
        wake = state.sim_time + timedelta(minutes=self._duration(outcome, intent))
        if tier_of(state.entities[person]) == 1:
            wake = max(wake, state.sim_time + timedelta(minutes=TIER1_EVERY))
        self.wake[person] = self._cap_for_promises(state, person, wake)
        self._inflight.discard(person)
        if person in self._poked:
            self._poked.discard(person)
            self.wake[person] = state.sim_time
        elif person in self._talked:
            # They spoke in a scene meanwhile: they will not sleep through what was said to them.
            self.wake[person] = min(self.wake[person], state.sim_time + timedelta(minutes=MIN_BEAT))
        self._talked.discard(person)
        self._wake_those_it_reaches(step, scene_events, person)
        self._after_scene(scene_events, person)

    def _after_scene(self, scene_events: list[Event], actor: str) -> None:
        """Those who just talked have had their turn; they decide again after a beat."""
        state = self.session.state
        talked = {e.actor for e in scene_events if e.actor in self.wake}
        for who in talked:
            if who != actor:
                self.wake[who] = state.sim_time + timedelta(minutes=MIN_BEAT)
                if who in self._inflight:
                    self._talked.add(who)

    def _wake_those_it_reaches(self, step: StepResult, scene_events: list[Event], actor: str) -> None:
        """Addressed, or loud enough to be heard, or weighty enough to matter: wake now."""
        state = self.session.state
        for observation in step.observations:
            who = observation.observer
            if who == actor or who not in self.wake:
                continue
            if observation.addressed and who not in self._engaged(scene_events):
                self.interrupt(who, state.sim_time)
        for event in step.events + scene_events:
            if not event.loud:
                continue
            for observation in step.observations:
                if observation.event_seq == event.seq and observation.observer != actor:
                    self.interrupt(observation.observer, state.sim_time)
        for observation in step.observations:
            who = observation.observer
            if who in self.wake and who != actor and self._weighty(who):
                self.interrupt(who, state.sim_time)

    @staticmethod
    def _engaged(scene_events: list[Event]) -> set[str]:
        return {e.actor for e in scene_events}

    def _weighty(self, person: str) -> bool:
        sim = self.sim
        if self.wake.get(person, sim.session.state.sim_time) - sim.session.state.sim_time < timedelta(minutes=SOON):
            return False
        fresh = sim.memory.list(
            self.session.branch_id, person, kinds=("observation", "utterance_heard"),
            after_seq=sim._last_decided(person), include_superseded=True,
        )
        return any(m.importance >= sim.salience for m in fresh)

    # -- one window ---------------------------------------------------------

    async def step(self, until: datetime | None = None) -> list[Event]:
        """Move to the next waking and let everyone due in the window act."""
        session = self.session
        state = session.state
        self._ensure(state)
        if not self.wake:
            return []
        nxt = min(self.wake.values())
        pending = self.sim.scheduler.pending(session.branch_id)
        if pending:
            nxt = min(nxt, pending[0][1])
        if until is not None:
            nxt = min(nxt, until)
        events: list[Event] = []
        minutes = int((nxt - state.sim_time).total_seconds() // 60)
        if (nxt - state.sim_time).total_seconds() % 60:
            minutes += 1
        if minutes > 0:
            session.store.journal_add(session.branch_id, state.seq, "clock", {"minutes": minutes, "tick_seq": state.seq})
            events += await advance_world(self.sim, minutes, state.seq)
            if self.on_clock is not None:
                events += await self.on_clock(minutes)
            state = session.state
            self._ensure(state)
        if until is not None and state.sim_time >= until:
            return events

        horizon = state.sim_time + timedelta(minutes=self.window)
        due = [p for p in self.residents(state) if self.wake.get(p, state.sim_time) <= horizon]
        if not due:
            return events
        self.windows += 1
        order = self.entropy.order("wake.order", due)
        session.store.journal_add(session.branch_id, state.seq, "window", {"t": state.sim_time.isoformat(), "order": order})
        tick_seq = state.seq
        plans = {p: self._plan_one(state, p) for p in order}
        tasks = [
            asyncio.create_task(self._decide_and_commit(state, p, plans[p], tick_seq)) for p in order
        ]
        before = state.seq
        await asyncio.gather(*tasks)
        # Memory upkeep for the people who just acted; nothing here changes events.
        await self._reflect(order, tick_seq)
        return events + session.store.events(session.branch_id, after=before)

    async def _decide_and_commit(self, state, person, plan, tick_seq):
        mode, block = plan
        self._inflight.add(person)
        self._poked.discard(person)
        decided = await self._decide(state, person, mode, block, tick_seq)
        await self._commit(person, decided, state, tick_seq)

    async def _reflect(self, people: list[str], tick_seq: int) -> None:
        from tinyworld.agents.persona import render

        sim = self.sim
        branch = self.session.branch_id
        state = self.session.state
        for person in people:
            entity = state.entities.get(person)
            if entity is None or persona_of(entity) is None:
                continue
            if sim.reflector.due(branch, person):
                await sim.reflector.reflect(
                    branch, person, render(entity, persona_of(entity)), state.seq, state.sim_time,
                    CallContext(branch, tick_seq, person),
                )
            await sim.compactor.compact(
                branch, person, render(entity, persona_of(entity)), state.seq, state.sim_time,
                CallContext(branch, tick_seq, person),
            )

    async def run_until(self, end: datetime, max_windows: int = 100000) -> int:
        """Run until the world's clock reaches ``end``. Returns the windows it took."""
        n = 0
        while self.session.state.sim_time < end and n < max_windows:
            before = (self.session.state.sim_time, self.session.state.seq)
            await self.step(until=end)
            n += 1
            if (self.session.state.sim_time, self.session.state.seq) == before:
                # Nothing moved: jump the clock so a stalled world still ends.
                state = self.session.state
                minutes = max(1, int((end - state.sim_time).total_seconds() // 60))
                self.session.store.journal_add(self.session.branch_id, state.seq, "clock", {"minutes": minutes, "tick_seq": state.seq})
                await advance_world(self.sim, minutes, state.seq)
        return n

    async def run_for(self, minutes: int) -> int:
        return await self.run_until(self.session.state.sim_time + timedelta(minutes=minutes))
