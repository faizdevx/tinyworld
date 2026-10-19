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
from tinyworld.world import chance, drives, petitions

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


def write_beliefs(sim: Simulation, rows: list) -> None:
    """(person, subject, predicate, value) as things the person now holds to be so."""
    from tinyworld.agents.beliefs import Belief

    state = sim.session.state
    for person, subject, predicate, value in rows:
        if person in state.entities:
            sim.beliefs.add(sim.session.branch_id, Belief(
                agent=person, subject=subject, predicate=predicate, value=value, confidence=0.75,
                origin="observation", as_of_seq=state.seq, as_of=state.sim_time,
            ))


def who_waits(town, person) -> bool:
    """Someone already on their way to pray does not decide again to."""
    return person.id in town._pilgrims


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
        desk=None,
        drives_on: bool = False,
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
        self.desk = desk  # a studio PetitionDesk, if a person sits at the podium
        self.drives_on = drives_on
        self._drive_seq = self.session.state.seq
        self._pilgrims: dict[str, tuple[str, dict]] = {}
        self.last_refused = ""
        self._channel = None
        if clocks is not None:
            clocks.on_clock = self._after_clock
        self.editions: dict[str, newspaper.Edition] = {}
        self._paper_day: date | None = None
        if drives_on:
            cast = drives.cast_draft(self.session.state)
            if cast is not None:
                self.commit([cast])
        if chaos is not None:
            self.commit([EventDraft(kind="system", actor="system", visibility="god_only",
                                    effects=[fx.SetRule(key=chance.RULE, value=chaos)])])

    # -- the one write path for the town's own events --------------------

    def commit(self, drafts: list[EventDraft], notes: list[tuple[str, str]] | None = None,
               beliefs: list[tuple[str, str, str, str]] | None = None) -> list[Event]:
        if not drafts:
            return []
        session = self.session
        session.store.journal_add(
            session.branch_id, session.state.seq, "drafts",
            {"drafts": [d.model_dump(mode="json") for d in drafts], "notes": [list(n) for n in notes or []],
             "beliefs": [list(b) for b in beliefs or []]},
        )
        events = session.commit(drafts, atomic=False).events
        if events and notes:
            self.sim.write_notes(notes, events[-1].seq, 0.8)
        if events and beliefs:
            write_beliefs(self.sim, beliefs)
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
        if self.drives_on:
            events += self._drives(minutes)
            events += self._prices()
        if self.petitioning:
            events += await self._petitions(tick_seq, minutes)
            events += await self._answers()
        if self.desk is not None:
            self.desk.sync()
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

    def _prices(self) -> list[Event]:
        """Once a simulated day, prices follow what there is to go round."""
        today = self.session.state.sim_time.date()
        if getattr(self, "_price_day", None) == today:
            return []
        first = getattr(self, "_price_day", None) is None
        self._price_day = today
        if first:
            return []
        from tinyworld.world import economy

        changes = economy.update_prices(self.session.state)
        if not changes:
            return []
        return self.commit([EventDraft(
            kind="system", actor="system", visibility="god_only", effects=changes,
            narration="Prices shift with what there is to buy.",
        )])

    # -- drives --------------------------------------------------------

    def _drives(self, minutes: int) -> list[Event]:
        """What has just happened moves what people want; with time they settle back."""
        session = self.session
        new = session.store.events(session.branch_id, after=self._drive_seq)
        self._drive_seq = session.state.seq
        changes = drives.consequences(session.state, new) + drives.drift(session.state, minutes)
        # One SetAttr per person: the later (drift) is applied to the state after the first.
        merged: dict[str, object] = {}
        for effect in changes:
            merged[effect.entity] = effect
        if not merged:
            return []
        events = self.commit([EventDraft(
            kind="system", actor="system", visibility="god_only", effects=list(merged.values()),
            narration="Wants shift with events.",
        )])
        self._drive_seq = session.state.seq
        return events

    # -- petitions -------------------------------------------------------

    async def _petitions(self, tick_seq: int, minutes: int = 60) -> list[Event]:
        state = self.session.state
        intents = []
        for person in sorted(state.people(), key=lambda p: p.id):
            if persona_of(person) is None or not person.location:
                continue
            if who_waits(self, person):
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
                if state.grid and petitions.holy_places(state) and not petitions.at_holy_place(state, person):
                    shrine = petitions.nearest_holy_place(state, person)
                    if shrine is None:
                        continue
                    self._pilgrims[person.id] = (text, args)
                    await self.apply([Intent(agent=person.id, verb=Verb.MOVE, target=shrine, text="go to pray")], tick_seq)
                    if self.clocks is not None:
                        self.clocks.interrupt(person.id, self.session.state.sim_time)
                    continue
                intents.append(Intent(agent=person.id, verb=Verb.PETITION, args=args, text=text))
        events: list[Event] = []
        # One at a time and in a recorded order: a batch would be shuffled by the Game Master's
        # seed, which a replay does not share.
        for intent in self.entropy.order("petition.order", intents):
            events += await self.apply([intent], tick_seq)
        events += await self._pilgrims_pray(tick_seq)
        return events

    async def _pilgrims_pray(self, tick_seq: int) -> list[Event]:
        """On a tile map a petition is made at a holy place: those who want to ask walk there first."""
        state = self.session.state
        events: list[Event] = []
        for who in sorted(self._pilgrims):
            person = state.entities.get(who)
            text, args = self._pilgrims[who]
            if person is None or not person.alive:
                del self._pilgrims[who]
            elif petitions.at_holy_place(state, person) and not person.attrs.get("route"):
                del self._pilgrims[who]
                events += await self.apply([Intent(agent=who, verb=Verb.PETITION, args=args, text=text)], tick_seq)
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

    @property
    def channel(self):
        if self._channel is None:
            from tinyworld.god.channel import GodChannel

            self._channel = GodChannel(self.sim.llm, world_digest=self.sim.world_digest)
        return self._channel

    async def answer(self, petition_id: str, power: str, text: str = "", effects: list | None = None,
                     command: str = "") -> list[Event]:
        """The god answers. ``command`` is what to do in the world, in words, through the god channel."""
        self.last_refused = ""
        state = self.session.state
        petition = petitions.get(state, petition_id)
        if command and petition is not None:
            made = await self.channel.submit(self.session, command)
            if not made.applied:
                self.last_refused = made.explanation or made.question or "that cannot be done"
                return []
            await self._witnessed(self.session.store.events(self.session.branch_id, after=made.event_seqs[0] - 1)[: len(made.event_seqs)])
            state = self.session.state
        here = [p.id for p in state.people_at(state.entities[petition.by].location)] if petition else []
        draft, notes = petitions.answer(state, petition_id, power, text, effects=effects, witnesses=here)
        beliefs = [(petition.by, *petitions.belief_of(petition, power))]
        events = self.commit([draft], notes, beliefs)
        await self._witnessed(events)
        if self.desk is not None:
            self.desk.sync()
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
