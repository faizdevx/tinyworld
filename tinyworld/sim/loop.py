"""The simulation tick: time passes, agents decide, the Game Master resolves,
witnesses remember."""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tinyworld.agents.agent import Acted, Agent
from tinyworld.agents.beliefs import BeliefStore
from tinyworld.agents import routine as daily
from tinyworld.agents.memory import EPISODIC, Compactor, ImportanceScorer, MemoryStore, NewMemory
from tinyworld.agents.persona import Persona, persona_of, render
from tinyworld.agents.planner import Planner
from tinyworld.agents.reflection import Reflector
from tinyworld.core import effects as fx
from tinyworld.core.events import Event, EventDraft, Intent, Outcome, Verb
from tinyworld.core.session import WorldSession
from tinyworld.core.state import Entity, Fact, Model, WorldState
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.master import GameMaster
from tinyworld.gm.perception import Observation, limit_attention, perceive
from tinyworld.god.compiler import PERSONA_SYSTEM, SpawnProfile
from tinyworld.llm.embed import Embedder, HashEmbedder
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext
from tinyworld.sim import tiers as tiering
from tinyworld.sim import commitments as pledges
from tinyworld.sim.budget import Budget
from tinyworld.sim.scene import Scenes, openings
from tinyworld.sim.schedule import Scheduler
from tinyworld.sim.scheduler import StepPolicy
from tinyworld.sim.step import apply_intents
from tinyworld.sim.tiers import TierPolicy, tier_of

MUNDANE_IMPORTANCE = 0.15
_MUNDANE = re.compile(
    r"\b(sleeps|waits|rests|works at [^.]*|goes from [^.]* to [^.]*)\.?$", re.IGNORECASE
)


def mundane(observation) -> bool:
    """Ordinary routine seen in passing: not worth asking a model about."""
    return (
        not observation.addressed
        and observation.speaker is None
        and _MUNDANE.search(observation.text.strip()) is not None
    )


PROMOTE_SYSTEM = (
    PERSONA_SYSTEM
    + "\n\nThis person already exists in the world and has so far been part of the "
    "background. Write who they are now. Stay consistent with their recorded history "
    "and keep any aptitudes they already have."
)

MOOD_SYSTEM = """You sum up the mood of ordinary people in a simulated place in two \
sentences, from the facts and recent events given. Plain and concrete; no forecasts."""


class Mood(Model):
    text: str


@dataclass
class TickResult:
    tick_seq: int
    events: list[Event] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    thoughts: dict[str, str] = field(default_factory=dict)
    memories_written: int = 0
    reflections: int = 0
    step_minutes: int = 0
    level: str = "ok"
    paused: bool = False
    promoted: list[str] = field(default_factory=list)
    # How each deciding agent was driven this tick: routine, react or deliberate.
    modes: dict[str, str] = field(default_factory=dict)
    scenes: int = 0
    scene_turns: int = 0
    commitments_made: int = 0
    commitments_resolved: int = 0

    @property
    def routine(self) -> int:
        return sum(1 for m in self.modes.values() if m == "routine")

    @property
    def reacted(self) -> int:
        return sum(1 for m in self.modes.values() if m == "react")

    @property
    def deliberated(self) -> int:
        return sum(1 for m in self.modes.values() if m == "deliberate")


class Simulation:
    def __init__(
        self,
        session: WorldSession,
        llm: StructuredLLM | None,
        *,
        embedder: Embedder | None = None,
        world_digest: str = "",
        step_minutes: int = 60,
        attention_limit: int = 8,
        reflect_threshold: float = 3.0,
        max_active_memories: int = 60,
        gm: GameMaster | None = None,
        policy: StepPolicy | None = None,
        tiers: TierPolicy | None = None,
        budget: Budget | None = None,
        routines: bool = True,
        scenes: bool = True,
        salience: float = 0.5,
        deliberate_hours: float = 12.0,
        max_jump_minutes: int = 480,
    ) -> None:
        self.session = session
        self.routines = routines
        self.salience = salience
        self.deliberate_hours = deliberate_hours
        self.max_jump_minutes = max_jump_minutes
        self.llm = llm
        self.world_digest = world_digest
        self.step_minutes = step_minutes
        self.attention_limit = attention_limit
        self.policy = policy
        self.tiers = tiers or TierPolicy()
        self.budget = budget
        store = session.store
        self.memory = MemoryStore(store, embedder or HashEmbedder())
        self.beliefs = BeliefStore(store)
        self.planner = Planner(self.memory)
        self.scheduler = Scheduler(store)
        self.scorer = ImportanceScorer(llm)
        self.reflector = Reflector(
            llm, self.memory, self.beliefs, threshold=reflect_threshold
        )
        self.compactor = Compactor(llm, self.memory, max_active=max_active_memories)
        self.gm = gm or GameMaster(
            Adjudicator(llm, world_digest=world_digest) if llm else None,
            seed=session.world_id,
        )
        self.agent = self.agent_tier1 = None
        if llm:
            self.agent = Agent(
                llm, self.memory, self.beliefs, self.planner, world_digest=world_digest
            )
            self.agent_tier1 = Agent(
                llm, self.memory, self.beliefs, self.planner, world_digest=world_digest,
                role="agent.act.tier1", memories_k=3, new_limit=5, beliefs_limit=4,
            )
        self.scenes = Scenes(self) if (scenes and llm is not None) else None
        self._last_events: list[Event] | None = None
        self._last_step: int | None = None

    # -- who acts -------------------------------------------------------

    def _acts_as(self, entity: Entity, step: int, cheap: bool) -> int | None:
        """The tier an entity acts at this tick, or None when it sits this one out."""
        if not entity.location or persona_of(entity) is None:
            return None
        tier = tier_of(entity)
        if tier >= 2:
            return None
        if tier == 0 and not cheap and not (
            self.budget is not None and self.budget.agent_over_cap(entity.id)
        ):
            return 0
        now = self.session.state.sim_time
        return 1 if self.tiers.tier1_turn(entity.id, now, step) else None

    def active_agents(
        self, state: WorldState, tick_seq: int, *, step: int | None = None, cheap: bool = False
    ) -> list[Entity]:
        """People who decide for themselves this tick."""
        step = step or self.step_minutes
        return sorted(
            (p for p in state.people() if self._acts_as(p, step, cheap) is not None),
            key=lambda p: p.id,
        )

    # -- two speeds: routine, react, deliberate -------------------------

    def _last_decided(self, agent_id: str) -> int:
        """The latest point at which this agent decided anything."""
        store, branch = self.session.store, self.session.branch_id
        return max(self._last_act_tick(agent_id), store.last_seq_by_actor(branch, agent_id))

    def _since_last_model_call(self, agent_id: str) -> timedelta | None:
        """Simulated time since the model last decided for this agent."""
        seq = self._last_act_tick(agent_id)
        if seq < 0:
            return None
        store, branch = self.session.store, self.session.branch_id
        found = store.event(branch, seq) if seq > 0 else None
        then = found.sim_time if found is not None else store.initial_state(branch).sim_time
        return self.session.state.sim_time - then

    def recent_actions(self, agent_id: str, n: int = 5) -> list[str]:
        store, branch = self.session.store, self.session.branch_id
        events = store.events(branch, actor=agent_id, limit=n, newest_first=True)
        return [e.narration for e in reversed(events) if e.kind in ("action", "utterance")]

    def mode_of(self, entity: Entity):
        """How this person decides now: by routine, by reaction, or afresh."""
        state = self.session.state
        if not self.routines:
            return "deliberate", None
        block = daily.current_block(state, entity)
        if block is None:
            return "deliberate", None
        branch = self.session.branch_id
        if block.kind == "promise":
            # A promise already made is kept by going there, not re-decided.
            return "routine", block
        since = self._since_last_model_call(entity.id)
        if since is None or since >= timedelta(hours=self.deliberate_hours):
            return "deliberate", block
        recent = self.recent_actions(entity.id, 3)
        if len(recent) == 3 and len(set(recent)) == 1:
            return "deliberate", block
        fresh = self.memory.list(
            branch, entity.id, kinds=EPISODIC,
            after_seq=self._last_decided(entity.id), include_superseded=True,
        )
        if any(m.importance >= self.salience for m in fresh):
            return "react", block
        return "routine", block

    def _before_promises(self, step: int) -> int:
        """Shorten ``step`` so a tick lands when someone must set out for a promise.

        Otherwise a long step can jump from before the lead time to after the
        due time, and the promise is broken without anyone having had a turn.
        """
        state = self.session.state
        for promise in state.open_commitments():
            keeper = state.entities.get(promise.by)
            lead = daily.promise_lead(state, keeper, promise) if keeper else None
            if lead is None or promise.kind != "meet":
                continue
            until = int(
                (promise.due - timedelta(minutes=lead) - state.sim_time).total_seconds() // 60
            )
            if 0 < until < step:
                step = until
        return max(1, step)

    def _routine_jump(self, step: int) -> tuple[int, dict[str, Intent]]:
        """Lengthen the step when everyone is on routine until a later boundary.

        Returns the new step and the routine intent of each person, decided at
        the start of the jump: they carry on with what their day says for the
        whole stretch, and the clock is moved once.
        """
        if not self.routines:
            return step, {}
        state = self.session.state
        minds = [
            p for p in state.people()
            if p.location and persona_of(p) is not None and tier_of(p) < 2
        ]
        if not minds:
            return step, {}
        blocks = {}
        for person in minds:
            mode, block = self.mode_of(person)
            if mode != "routine" or block is None:
                return step, {}
            blocks[person.id] = block
        horizon = min(
            [b.minutes_left(state.sim_time) for b in blocks.values()]
            + [self.max_jump_minutes]
        )
        pending = self.scheduler.pending(self.session.branch_id)
        if pending:
            wait = int((pending[0][1] - state.sim_time).total_seconds() // 60)
            horizon = min(horizon, max(1, wait))
        for promise in state.open_commitments():
            keeper = state.entities.get(promise.by)
            lead = daily.promise_lead(state, keeper, promise) if keeper else None
            wait = int((promise.due - state.sim_time).total_seconds() // 60)
            # Stop early enough that whoever promised can still set out.
            horizon = min(horizon, max(1, wait - (lead if lead is not None else 0)))
        if horizon <= step:
            return step, {}
        intents = {}
        for person in minds:
            intent = daily.routine_intent(state, person, blocks[person.id], horizon)
            # Someone still on their way to their place: let the ordinary
            # step carry them there before time is skipped.
            if intent is None or intent.verb is Verb.MOVE:
                return step, {}
            intents[person.id] = intent
        return horizon, intents

    # -- memory ---------------------------------------------------------

    def _last_act_tick(self, agent_id: str) -> int:
        store = self.session.store
        clause, params = store.lineage_clause(
            self.session.branch_id, "tick_seq", before=True
        )
        row = store.query(
            f"SELECT MAX(tick_seq) AS last FROM llm_calls WHERE {clause}"
            " AND agent=? AND role LIKE 'agent.act%'",
            params + [agent_id],
        )[0]
        return row["last"] if row["last"] is not None else -1

    async def _remember(
        self, observer: Entity, observations: list[Observation], tick_seq: int
    ) -> int:
        branch = self.session.branch_id
        kept = limit_attention(observations, self.attention_limit)
        if not kept:
            return 0
        persona = persona_of(observer)
        who = render(observer, persona) if persona else observer.name
        worth = [o for o in kept if not mundane(o)]
        asked = await self.scorer.score(
            who,
            [o.text for o in worth],
            CallContext(branch, tick_seq, observer.id),
            addressed=[o.addressed for o in worth],
        ) if worth else []
        by_id = {id(o): s for o, s in zip(worth, asked)}
        scores = [by_id.get(id(o), MUNDANE_IMPORTANCE) for o in kept]
        items = [
            NewMemory(
                kind="utterance_heard"
                if o.speaker and o.speaker != observer.id
                else "observation",
                text=o.text,
                created_seq=o.event_seq,
                sim_time=o.sim_time,
                importance=score,
                confidence=o.confidence,
                source_events=[o.event_seq],
                participants=[p for p in o.participants if p != observer.id],
            )
            for o, score in zip(kept, scores)
        ]
        written = self.memory.write(branch, observer.id, items)
        for observation, memory in zip(kept, written):
            self.beliefs.update_from_observation(
                branch, self.session.state, observation, memory.id
            )
        return len(written)

    async def remember(self, observations: list[Observation], tick_seq: int) -> int:
        """Give observations to everyone who has a mind to keep them in."""
        state = self.session.state
        by_observer: dict[str, list[Observation]] = {}
        for observation in observations:
            by_observer.setdefault(observation.observer, []).append(observation)
        rememberers = [
            state.entities[o] for o in sorted(by_observer)
            if o in state.entities and persona_of(state.entities[o]) is not None
        ]
        counts = await asyncio.gather(
            *(self._remember(e, by_observer[e.id], tick_seq) for e in rememberers)
        )
        return sum(counts)

    async def remember_events(
        self, seqs: list[int], tick_seq: int, *, journal: bool = True
    ) -> int:
        """Let witnesses remember events committed outside a tick, such as a god's.

        Perception is recomputed from the stored log, so a replay that repeats
        this call produces the same memories.
        """
        if not seqs:
            return 0
        store, branch = self.session.store, self.session.branch_id
        if journal:
            store.journal_add(branch, self.session.state.seq, "remember", {"seqs": seqs, "tick_seq": tick_seq})
        observations = []
        for seq in seqs:
            event = store.event(branch, seq)
            if event is not None:
                observations += perceive(event, store.state_at(branch, seq))
        return await self.remember(observations, tick_seq)

    # -- notes and promises ---------------------------------------------

    def write_notes(
        self, notes: list[tuple[str, str]], seq: int, importance: float = 0.7
    ) -> None:
        """A first-hand memory for each (person, text), at event ``seq``."""
        state = self.session.state
        for agent_id, text in notes:
            entity = state.entities.get(agent_id)
            if entity is None or persona_of(entity) is None:
                continue
            self.memory.write(
                self.session.branch_id, agent_id,
                [
                    NewMemory(
                        kind="observation", text=text, created_seq=seq,
                        sim_time=state.sim_time, importance=importance,
                        source_events=[seq] if seq > 0 else [],
                    )
                ],
            )

    def settle_commitments(self) -> list[Event]:
        """Resolve promises that have fallen due, and let both sides know."""
        session = self.session
        events: list[Event] = []
        for draft, notes in pledges.settle(
            session.state, session.store, session.branch_id
        ):
            committed = session.commit([draft], atomic=False).events
            if committed:
                events += committed
                self.write_notes(notes, committed[-1].seq, 0.8)
        return events

    # -- promotion ------------------------------------------------------

    def history_of(self, entity: Entity, limit: int = 30) -> list[Event]:
        """Recorded events that name this entity, oldest first."""
        store, branch = self.session.store, self.session.branch_id
        found = [
            event
            for kind in ("chronicle", "god")
            for event in store.events(branch, kind=kind)
            if entity.name in event.narration
            or entity.id in event.model_dump_json(include={"effects"})
        ]
        return sorted(found, key=lambda e: e.seq)[-limit:]

    async def _backfill(
        self, entity: Entity, history: list[Event], tick_seq: int
    ) -> SpawnProfile:
        state = self.session.state
        existing = persona_of(entity)
        age = tiering.age_of(entity, state.sim_time)
        fallback = SpawnProfile(
            age=age if age is not None else 30,
            occupation=str(entity.attrs.get("occupation", "")),
            persona=existing
            or Persona(summary=f"{entity.name}, one of the townspeople."),
        )
        if self.llm is None:
            return fallback
        era = state.rules.get("era")
        reply = await self.llm.call(
            "agent.persona",
            SpawnProfile,
            system=PROMOTE_SYSTEM,
            stable_context="About this world:\n" + self.world_digest if self.world_digest else "",
            user=(
                f"Now: {state.sim_time:%d %B %Y}. Era: {era or 'see above'}.\n"
                f"Name: {entity.name}\nAge now: {fallback.age}\n"
                f"Occupation on record: {fallback.occupation or '(none)'}\n"
                f"Existing character sheet: "
                f"{existing.model_dump_json() if existing else '(none)'}\n"
                "Recorded history:\n"
                + ("\n".join(f"- {e.sim_time:%b %Y}: {e.narration}" for e in history) or "- (nothing recorded)")
            ),
            context=CallContext(self.session.branch_id, tick_seq, f"{entity.id}:persona"),
            fallback=fallback,
            max_tokens=2000,
        )
        profile = reply.value
        if existing is not None:
            # Inborn gifts are kept whatever the model writes.
            profile.persona.aptitudes = {**profile.persona.aptitudes, **existing.aptitudes}
        if not profile.persona.knowledge.era and isinstance(era, str):
            profile.persona.knowledge.era = era
        return profile

    async def promote(
        self,
        entity_ids: list[str],
        *,
        refresh: bool = False,
        reason: str = "drawn into events",
        journal: bool = False,
    ) -> list[str]:
        """Make background people into deciding agents, with a persona and a past.

        Pass ``journal=True`` when the promotion is decided from outside the
        tick, so that a replay repeats it.
        """
        state = self.session.state
        if journal and entity_ids:
            self.session.store.journal_add(
                self.session.branch_id, state.seq, "promote",
                {"ids": list(entity_ids), "reason": reason},
            )
        tick_seq = state.seq
        effects: list = []
        promoted: list[tuple[Entity, list[Event]]] = []
        for entity_id in entity_ids:
            entity = state.entities.get(entity_id)
            if (
                entity is None or entity.kind != "person" or not entity.alive
                or not tiering.old_enough(entity, state.sim_time)
            ):
                continue
            needs_persona = refresh or persona_of(entity) is None
            if tier_of(entity) == 0 and not needs_persona:
                continue
            history = self.history_of(entity)
            if needs_persona:
                profile = await self._backfill(entity, history, tick_seq)
                effects.append(
                    fx.SetAttr(entity=entity.id, key="persona", value=profile.persona.model_dump())
                )
                if profile.occupation:
                    effects.append(
                        fx.SetAttr(entity=entity.id, key="occupation", value=profile.occupation)
                    )
            if tier_of(entity) != 0:
                effects.append(fx.SetAttr(entity=entity.id, key="tier", value=0))
            if entity.attrs.get("status") == "child":
                effects.append(fx.SetAttr(entity=entity.id, key="status", value=None))
            promoted.append((entity, history))
        if not effects:
            return []
        self.session.commit(
            [
                EventDraft(
                    kind="system", actor="system", visibility="god_only", effects=effects,
                    narration=f"Promoted ({reason}): "
                    + ", ".join(entity.name for entity, _ in promoted) + ".",
                )
            ]
        )
        # A promoted person remembers the life the chronicle says they led.
        state = self.session.state
        for entity, history in promoted:
            already = any(
                m.text.startswith("My life so far")
                for m in self.memory.list(self.session.branch_id, entity.id, kinds=("summary",))
            )
            if not history or already:
                continue
            self.memory.write(
                self.session.branch_id,
                entity.id,
                [
                    NewMemory(
                        kind="summary",
                        text="My life so far: "
                        + " ".join(e.narration for e in history if e.narration),
                        created_seq=state.seq,
                        sim_time=state.sim_time,
                        importance=0.7,
                        source_events=[e.seq for e in history],
                    )
                ],
            )
        return [entity.id for entity, _ in promoted]

    # -- upkeep ---------------------------------------------------------

    def _crossed(self, before: datetime, after: datetime) -> bool:
        period = self.tiers.tier2_every_minutes * 60
        epoch = tiering.EPOCH
        return int((before - epoch).total_seconds() // period) != int(
            (after - epoch).total_seconds() // period
        )

    async def _mood(self, tick_seq: int) -> EventDraft | None:
        if self.llm is None:
            return None
        state = self.session.state
        recent = self.session.store.events(
            self.session.branch_id, limit=20, newest_first=True
        )
        from tinyworld.gm.context import describe_facts

        reply = await self.llm.call(
            "tier2.summary",
            Mood,
            system=MOOD_SYSTEM,
            stable_context="About this world:\n" + self.world_digest if self.world_digest else "",
            user="Standing facts:\n"
            + describe_facts(state, limit=15)
            + "\n\nRecent events:\n"
            + ("\n".join(f"- {e.narration}" for e in reversed(recent) if e.narration) or "- none"),
            context=CallContext(self.session.branch_id, tick_seq, "tier2"),
            fallback=Mood(text=""),
            max_tokens=300,
        )
        if not reply.ok or not reply.value.text.strip():
            return None
        return EventDraft(
            kind="system", actor="system", visibility="god_only",
            effects=[
                fx.AssertFact(
                    fact=Fact(
                        id="fact:public_mood", text="Public mood: " + reply.value.text.strip(),
                        subject="public", predicate="mood", value=reply.value.text.strip(),
                    )
                )
            ],
            narration="Public mood noted.",
        )

    async def upkeep(self, before: datetime, tick_seq: int, periods: int = 1) -> list[Event]:
        """Ageing, demotion and background drift after time has moved."""
        session = self.session
        drafts: list[EventDraft] = []
        aged = tiering.aging_draft(session.state)
        if aged is not None:
            drafts.append(aged)
        idle = self.tiers.demotions(session.store, session.branch_id, session.state)
        if idle:
            drafts.append(
                tiering.tier_draft({i: 1 for i in idle}, "Demoted after a long quiet spell.")
            )
        if periods > 1 or self._crossed(before, session.state.sim_time):
            drift = tiering.background_drift(session.state, session.world_id, periods)
            if drift is not None:
                drafts.append(drift)
            mood = await self._mood(tick_seq)
            if mood is not None:
                drafts.append(mood)
        events = session.commit(drafts, atomic=False).events if drafts else []

        grown = [
            p.id for p in session.state.people()
            if p.attrs.get("status") == "child"
            and tiering.old_enough(p, session.state.sim_time)
        ]
        if grown:
            await self.promote(grown, refresh=True, reason="come of age")
        return events

    def record_birth_dates(self) -> list[Event]:
        """Must run before time moves, while stored ages are still current."""
        draft = tiering.birth_dates_draft(self.session.state)
        return self.session.commit([draft]).events if draft is not None else []

    # -- the tick -------------------------------------------------------

    async def tick(
        self, step_minutes: int | None = None, *, journal: bool = True
    ) -> TickResult:
        """Advance the world by one step. ``step_minutes`` overrides the step policy."""
        session = self.session
        branch = session.branch_id
        tick_seq = session.state.seq
        result = TickResult(tick_seq)

        level = self.budget.level() if self.budget else "ok"
        result.level = level
        if level == "pause":
            result.paused = True
            return result
        cheap = level == "demote"
        if step_minutes is not None:
            step = step_minutes
        elif self.policy is not None and self._last_events is not None:
            step = self.policy.next_step(
                session.state, self._last_events, self._last_step, lengthen=level != "ok"
            )
        else:
            step = self.policy.base_minutes if self.policy else self.step_minutes
        jumped: dict[str, Intent] = {}
        if step_minutes is None:
            step = self._before_promises(step)
            step, jumped = self._routine_jump(step)
        result.step_minutes = step
        if journal:
            session.store.journal_add(branch, tick_seq, "tick", {"step": step})

        # 1. Time passes; queued events fire; the background is kept up.
        result.events += self.record_birth_dates()
        before = session.state.sim_time
        clock = EventDraft(
            kind="system", actor="system", visibility="god_only",
            effects=[fx.AdvanceTime(minutes=step)],
        )
        due = self.scheduler.pending(branch, due_by=before + timedelta(minutes=step))
        opening = session.commit(
            [clock] + [draft for _, _, draft in due], atomic=False, observe=perceive
        )
        # A queued event fires once, even if the world could no longer take it.
        self.scheduler.mark_done(branch, [item[0] for item in due], session.state.seq)
        result.events += opening.events
        observations = [o for batch in opening.observed for o in batch]
        result.events += await self.upkeep(before, tick_seq)
        settled = self.settle_commitments()
        result.events += settled
        result.commitments_resolved = len(settled)

        # 2. Everyone decides at once, from the same view of the world.
        state = session.state
        deciders = []
        by_routine: list[Acted] = []
        for entity in self.active_agents(state, tick_seq, step=step, cheap=cheap):
            tier = self._acts_as(entity, step, cheap)
            agent = self.agent if tier == 0 else self.agent_tier1
            if entity.id in jumped:
                by_routine.append(Acted(jumped[entity.id], "routine", True, None))
                result.modes[entity.id] = "routine"
                continue
            if tier == 0:
                mode, block = self.mode_of(entity)
            else:
                mode, block = "deliberate", None
            if mode == "routine" and block is not None:
                intent = daily.routine_intent(state, entity, block, step)
                if intent is not None:
                    by_routine.append(Acted(intent, "routine", True, None))
                    result.modes[entity.id] = "routine"
                    continue
                mode = "react"
            if agent is not None:
                result.modes[entity.id] = mode
                deciders.append((entity, agent, daily.hint(state, entity, block)))
        modelled: list[Acted] = await asyncio.gather(
            *(
                agent.act(
                    state, entity, branch,
                    CallContext(branch, tick_seq, entity.id),
                    self._last_act_tick(entity.id),
                    hint=hint,
                    recent=self.recent_actions(entity.id),
                    promises=pledges.lines_for(state, entity.id),
                )
                for entity, agent, hint in deciders
            )
        )
        acted: list[Acted] = sorted(
            by_routine + list(modelled), key=lambda a: a.intent.agent
        )
        result.thoughts = {a.intent.agent: a.thought for a in acted}

        # 3. The Game Master decides what actually happens.
        step_result = await apply_intents(
            session, self.gm, [a.intent for a in acted], CallContext(branch, tick_seq),
            causes={a.intent.agent: a.causes for a in acted},
        )
        result.events += step_result.events
        result.outcomes = step_result.outcomes
        observations += step_result.observations

        # 3b. A line addressed to someone is answered, within the same tick.
        scene_events: list[Event] = []
        if self.scenes is not None:
            for speaker, listener, line in openings(
                session.state, step_result.events, self.scenes.max_scenes
            ):
                scene = await self.scenes.run(tick_seq, speaker, listener, line)
                scene_events += scene.events
                observations += scene.observations
                result.scenes += scene.scenes
                result.scene_turns += scene.turns
                result.commitments_made += scene.commitments
            result.events += scene_events

        # 4. People drawn into events start deciding for themselves.
        result.promoted = await self.promote(
            self.tiers.involved(session.state, step_result.events + scene_events)
        )

        # 5. Witnesses remember and update what they believe.
        result.memories_written = await self.remember(observations, tick_seq)

        # 6. Reflection and memory upkeep for those who have enough to chew on.
        state = session.state
        minds = [
            p for p in sorted(state.people(), key=lambda p: p.id)
            if persona_of(p) is not None and tier_of(p) < 2
        ]
        due_to_reflect = [e for e in minds if self.reflector.due(branch, e.id)]
        reflected = await asyncio.gather(
            *(
                self.reflector.reflect(
                    branch, e.id, render(e, persona_of(e)), state.seq, state.sim_time,
                    CallContext(branch, tick_seq, e.id),
                )
                for e in due_to_reflect
            )
        )
        result.reflections = sum(1 for memories in reflected if memories)
        await asyncio.gather(
            *(
                self.compactor.compact(
                    branch, e.id, render(e, persona_of(e)), state.seq, state.sim_time,
                    CallContext(branch, tick_seq, e.id),
                )
                for e in minds
            )
        )
        self._last_events = result.events
        self._last_step = step
        return result

    async def run(self, ticks: int) -> list[TickResult]:
        results = []
        for _ in range(ticks):
            result = await self.tick()
            results.append(result)
            if result.paused:
                break
        return results
