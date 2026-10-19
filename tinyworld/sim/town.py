"""The living town: the world's ordinary tick, plus fortune, petitions and a paper.

``Town`` wraps a ``Simulation`` and adds what v7 puts around it:

- chance events scaled by the ``chaos`` rule (world/chance.py);
- residents who petition the god when they need to (world/petitions.py), and a
  policy that answers them (a person, an AI god, or silence after a timeout);
- one newspaper edition per simulated day (sim/newspaper.py).

Everything it does to the world goes through the one writer and is written to
the branch journal, so a replay repeats it: ``drafts`` for events it commits
itself, ``town_intents`` for resident actions that go through the Game Master.
"""

from collections.abc import Callable
from datetime import date

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy
from tinyworld.core.events import Event, EventDraft, Intent, Verb
from tinyworld.core.state import WorldState
from tinyworld.llm.types import CallContext
from tinyworld.sim import newspaper
from tinyworld.sim.loop import Simulation, TickResult
from tinyworld.sim.step import apply_intents
from tinyworld.world import chance, petitions

# (power, text, effects) for a petition, or None to leave it waiting.
Answerer = Callable[[WorldState, petitions.Petition, Entropy], "tuple[str, str, list] | None"]


def auto_god(state: WorldState, petition: petitions.Petition, entropy: Entropy):
    """A stand-in god for experiments: answers by a recorded draw, mostly kindly."""
    power = entropy.choice("god.power", ["grant", "whisper", "whisper", "sign", "refuse", "refuse", "ignore"])
    if power == "grant":
        goods = sorted(
            e.id for e in state.entities.values() if e.kind == "resource" and e.id in
            (state.entities[petition.by].inventory or state.entities)
        )
        held = sorted(state.entities[petition.by].inventory) or goods[:1]
        effects = [fx.ChangeQuantity(holder=petition.by, item=held[0], delta=2)] if held else []
        return power, "Take this, and be at peace.", effects
    if power == "whisper":
        return power, "You are not forgotten. Be patient.", []
    if power == "sign":
        return power, "Light falls where none was expected.", []
    if power == "refuse":
        return power, "That is not mine to give.", []
    return "ignore", "", []


class Town:
    def __init__(
        self,
        sim: Simulation,
        entropy: Entropy,
        *,
        petitioning: bool = True,
        paper: bool = True,
        god: Answerer | None = auto_god,
        chaos: float | None = None,
        write_petitions: bool = False,
        clocks=None,
        creators=None,
    ) -> None:
        # With a model, the petition is written by it from the person's situation.
        self.write_petitions = write_petitions and sim.llm is not None
        self.sim = sim
        self.session = sim.session
        self.entropy = entropy
        self.petitioning = petitioning
        self.paper = paper
        self.god = god
        # With ``clocks`` (an AsyncSimulation) residents live on their own clocks instead of ticks.
        self.clocks = clocks
        # The builders who answer when someone reaches the edge of the known ground.
        self.creators = creators
        if clocks is not None:
            clocks.on_clock = self._after_clock
        self.editions: dict[str, newspaper.Edition] = {}
        self._paper_day: date | None = None
        if chaos is not None:
            self.commit([EventDraft(kind="system", actor="system", visibility="god_only",
                                    effects=[fx.SetRule(key=chance.RULE, value=chaos)])])

    # -- the one write path for the town's own events --------------------

    def commit(self, drafts: list[EventDraft], notes: list[tuple[str, str]] | None = None) -> list[Event]:
        if not drafts:
            return []
        session = self.session
        session.store.journal_add(
            session.branch_id, session.state.seq, "drafts",
            {"drafts": [d.model_dump(mode="json") for d in drafts], "notes": [list(n) for n in notes or []]},
        )
        events = session.commit(drafts, atomic=False).events
        if events and notes:
            self.sim.write_notes(notes, events[-1].seq, 0.8)
        return events

    async def _witnessed(self, events: list[Event]) -> None:
        if events:
            await self.sim.remember_events([e.seq for e in events], self.session.state.seq)

    # -- one advance -----------------------------------------------------

    async def advance(self, minutes: int | None = None) -> TickResult:
        if self.clocks is not None:
            seq = self.session.state.seq
            await self.clocks.run_for(minutes or 60)
            return TickResult(seq, events=self.session.store.events(self.session.branch_id, after=seq))
        result = await self.sim.tick(minutes)
        result.events += await self._after_clock(result.step_minutes or minutes or 60, result.tick_seq)
        return result

    async def _after_clock(self, minutes: int, tick_seq: int | None = None) -> list[Event]:
        """What the town adds each time the clock moves: fortune, petitions, answers, the paper."""
        events: list[Event] = []
        tick_seq = self.session.state.seq if tick_seq is None else tick_seq
        fortune = chance.roll(self.session.state, minutes, self.entropy)
        if fortune is not None:
            made = self.commit([fortune.draft])
            events += made
            await self._witnessed(made)
        if self.petitioning:
            events += await self._petitions(tick_seq, minutes)
            events += await self._answers()
        if self.creators is not None:
            events += await self._grow()
        if self.paper:
            events += self._newspaper()
        return events

    # -- the map grows -----------------------------------------------------

    async def _grow(self) -> list[Event]:
        """Raise a request for ground someone can see, and answer one waiting request."""
        from tinyworld.core.reducers import EffectError, apply_effect
        from tinyworld.genesis import layout
        from tinyworld.world import frontier

        events: list[Event] = []
        state = self.session.state
        if not state.grid:
            return events
        for key, person in frontier.scan(state):
            draft = frontier.request_draft(self.session.state, key, person, "seen")
            if draft is not None:
                events += self.commit([draft])
        state = self.session.state
        waiting = frontier.pending(state)
        if not waiting:
            return events
        request = waiting[0]

        def refuse(why: str) -> list[Event]:
            return self.commit([EventDraft(
                kind="system", actor="system", visibility="god_only",
                effects=[frontier.settled_effect(self.session.state, request.chunk, "refused", [])],
                narration=f"The ground at {request.chunk} stays unknown: {why}",
            )])

        result = await self.creators.answer(state, request, self.entropy, self.session.branch_id)
        if isinstance(result, str):
            return events + refuse(result)
        try:
            drafts = layout.extend(state, request.chunk, result.places, self.entropy)
            working = state.model_copy(deep=True)
            for draft in drafts:  # the reducers have the last word
                for effect in draft.effects:
                    apply_effect(working, effect)
        except (ValueError, EffectError) as exc:
            return events + refuse(f"it could not be laid out ({exc})")
        names = [p.name for p in result.places]
        drafts.append(EventDraft(
            kind="system", actor="system", visibility="god_only",
            effects=[frontier.settled_effect(state, request.chunk, "generated", names)],
            narration=f"Chunk {request.chunk} is settled.",
        ))
        return events + self.commit(drafts)

    async def run(self, ticks: int, minutes: int | None = None) -> list[TickResult]:
        return [await self.advance(minutes) for _ in range(ticks)]

    # -- petitions -------------------------------------------------------

    async def _petitions(self, tick_seq: int, minutes: int = 60) -> list[Event]:
        state = self.session.state
        intents = []
        for person in sorted(state.people(), key=lambda p: p.id):
            if persona_of(person) is None or not person.location:
                continue
            if petitions.due_to_petition(state, person, self.entropy, minutes):
                if self.write_petitions:
                    text, args = await petitions.compose_with_model(
                        self.sim.llm, state, person, self.sim.recent_actions(person.id),
                        CallContext(self.session.branch_id, tick_seq, f"{person.id}:petition"),
                        self.sim.world_digest,
                    )
                else:
                    text, args = petitions.compose(person, self.entropy)
                intents.append(Intent(agent=person.id, verb=Verb.PETITION, args=args, text=text))
        events: list[Event] = []
        # One at a time and in a recorded order: a batch would be shuffled by the Game Master's
        # seed, which a replay does not share.
        for intent in self.entropy.order("petition.order", intents):
            events += await self.apply([intent], tick_seq)
        return events

    async def apply(self, intents: list[Intent], tick_seq: int) -> list[Event]:
        """Resident actions chosen by the town itself, through the Game Master like any other."""
        session = self.session
        session.store.journal_add(
            session.branch_id, session.state.seq, "town_intents",
            {"intents": [i.model_dump(mode="json") for i in intents], "tick_seq": tick_seq},
        )
        step = await apply_intents(session, self.sim.gm, intents, CallContext(session.branch_id, tick_seq))
        await self.sim.remember(step.observations, tick_seq)
        return step.events

    async def _answers(self) -> list[Event]:
        state = self.session.state
        out: list[Event] = []
        for petition in petitions.open_petitions(state):
            if self.god is None:
                continue
            decided = self.god(state, petition, self.entropy)
            if decided is None:
                continue
            power, text, effects = decided
            out += await self.answer(petition.id, power, text, effects)
            state = self.session.state
        # Nobody answered in time: silence, which is also an answer.
        for draft, notes in petitions.resolve_silence(self.session.state):
            events = self.commit([draft], notes)
            out += events
            await self._witnessed(events)
        return out

    async def answer(self, petition_id: str, power: str, text: str = "", effects: list | None = None) -> list[Event]:
        state = self.session.state
        petition = petitions.get(state, petition_id)
        here = [p.id for p in state.people_at(state.entities[petition.by].location)] if petition else []
        draft, notes = petitions.answer(state, petition_id, power, text, effects=effects, witnesses=here)
        events = self.commit([draft], notes)
        await self._witnessed(events)
        return events

    # -- the paper -------------------------------------------------------

    def _newspaper(self) -> list[Event]:
        """When a day has ended, print its edition."""
        state = self.session.state
        today = state.sim_time.date()
        if self._paper_day is None:
            self._paper_day = today
            return []
        if today == self._paper_day:
            return []
        day, self._paper_day = self._paper_day, today
        events = self.session.store.events(self.session.branch_id)
        edition = newspaper.write(events, day, state)
        self.editions[day.isoformat()] = edition
        newspaper.save(self.session.store, self.session.world_id, edition)
        draft = newspaper.publish_draft(state, edition)
        return self.commit([draft]) if draft is not None else []
