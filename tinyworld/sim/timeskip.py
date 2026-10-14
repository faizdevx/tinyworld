"""Skipping long stretches of time, one chronicled period after another."""

from dataclasses import dataclass, field
from datetime import timedelta

from tinyworld.agents.memory import NewMemory
from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import Event, EventDraft
from tinyworld.llm.types import CallContext
from tinyworld.sim.chronicler import Chronicler, outcome_effects, validate
from tinyworld.sim.loop import Simulation
from tinyworld.sim.tiers import tier_of

DAY = 24 * 60

# (longest skip this period length is used for, period length), in minutes.
_PERIODS = [
    (14 * DAY, DAY),
    (120 * DAY, 7 * DAY),
    (3 * 365 * DAY, 30 * DAY),
]
_YEAR = 365 * DAY


def period_length(total_minutes: int) -> int:
    for longest, period in _PERIODS:
        if total_minutes <= longest:
            return period
    return _YEAR


def plan(total_minutes: int) -> list[int]:
    """Period lengths that add up to the skip."""
    if total_minutes <= 0:
        raise ValueError("a skip must move time forward")
    period = period_length(total_minutes)
    full, rest = divmod(total_minutes, period)
    return [period] * full + ([rest] if rest else [])


def label(minutes: int) -> str:
    if minutes >= _YEAR:
        years = round(minutes / _YEAR)
        return f"{years} year{'s' if years != 1 else ''}"
    if minutes >= 28 * DAY:
        months = round(minutes / (30 * DAY))
        return f"{months} month{'s' if months != 1 else ''}"
    if minutes >= 7 * DAY:
        weeks = round(minutes / (7 * DAY))
        return f"{weeks} week{'s' if weeks != 1 else ''}"
    days = max(1, round(minutes / DAY))
    return f"{days} day{'s' if days != 1 else ''}"


@dataclass
class SkipResult:
    requested_minutes: int
    skipped_minutes: int = 0
    periods: int = 0
    events: list[Event] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    stopped: str | None = None

    @property
    def complete(self) -> bool:
        return self.skipped_minutes == self.requested_minutes


class TimeSkip:
    def __init__(self, sim: Simulation, chronicler: Chronicler | None = None) -> None:
        self.sim = sim
        self.chronicler = chronicler or Chronicler(sim.llm, world_digest=sim.world_digest)

    async def skip(self, minutes: int, *, journal: bool = True) -> SkipResult:
        """Advance the world by ``minutes``, chronicling what happened on the way.

        Stops early, with the reason in ``stopped``, when the budget runs out.
        """
        sim = self.sim
        session = sim.session
        branch = session.branch_id
        result = SkipResult(requested_minutes=minutes)
        plan(minutes)  # rejects a non-positive skip before anything is recorded
        if journal:
            session.store.journal_add(branch, session.state.seq, "skip", {"minutes": minutes})
        result.events += sim.record_birth_dates()

        for period in plan(minutes):
            if sim.budget is not None and sim.budget.level() == "pause":
                result.stopped = "budget"
                break
            tick_seq = session.state.seq
            before = session.state.sim_time
            until = before + timedelta(minutes=period)
            recent = [
                e for e in session.store.events(branch, limit=40, newest_first=True)
                if e.kind in ("chronicle", "god", "action", "utterance") and e.narration
            ][:12][::-1]
            proposal, trace_id = await self.chronicler.propose(
                session.state, until, recent, CallContext(branch, tick_seq)
            )

            # Time moves first, so everything below is judged at the period's end.
            clock = EventDraft(
                kind="system", actor="system", visibility="god_only",
                effects=[fx.AdvanceTime(minutes=period)],
                narration=f"{label(period).capitalize()} "
                f"{'passes' if label(period).startswith('1 ') else 'pass'}. "
                + (proposal.summary.strip() or "Nothing much changed."),
            )
            due = sim.scheduler.pending(branch, due_by=until)
            opened = session.commit([clock] + [d for _, _, d in due], atomic=False)
            sim.scheduler.mark_done(branch, [item[0] for item in due], session.state.seq)
            result.events += opened.events

            # Each proposed event is validated against the world as the earlier
            # ones left it; what does not hold is dropped, not repaired.
            working = session.state
            drafts: list[EventDraft] = []
            accepted = []
            for proposed in proposal.events:
                after, reason = validate(working, proposed, session.registry)
                extra = outcome_effects(working, proposed) if after is not None else []
                if after is not None and extra:
                    widened = proposed.model_copy(
                        update={"effects": list(proposed.effects) + extra}
                    )
                    after, reason = validate(working, widened, session.registry)
                    proposed = widened if after is not None else proposed
                if after is None:
                    result.rejected.append((proposed.narration, reason))
                    continue
                working = after
                accepted.append(proposed)
                names = [
                    session.state.entities[p].name
                    for p in proposed.participants
                    if p in session.state.entities
                ]
                drafts.append(
                    EventDraft(
                        kind="chronicle",
                        actor="gm",
                        # Earlier history involving the same people led here.
                        causes=[
                            e.seq for e in recent
                            if any(name in e.narration for name in names)
                        ][-5:],
                        location=proposed.location or None,
                        effects=list(proposed.effects),
                        narration=proposed.narration,
                        visibility="god_only",
                        trace_id=trace_id,
                    )
                )
            committed = session.commit(drafts, atomic=False)
            result.events += committed.events
            for draft, reason in committed.rejected:
                result.rejected.append((draft.narration, reason))

            scale = max(1, period // sim.tiers.tier2_every_minutes)
            result.events += await sim.upkeep(before, tick_seq, periods=min(scale, 30))

            # People carry the stretch as one memory, with their own part in it.
            state = session.state
            span = f"Over {label(period)} (to {state.sim_time:%B %Y})"
            summary = proposal.summary.strip() or "nothing much changed."
            for person in sorted(state.people(), key=lambda p: p.id):
                # Only those with a mind of their own carry memories.
                if persona_of(person) is None or tier_of(person) >= 2:
                    continue
                own = [e for e in accepted if person.id in e.participants]
                text = f"{span}: {summary}"
                if own:
                    text += " For me: " + " ".join(e.narration for e in own)
                sim.memory.write(
                    branch,
                    person.id,
                    [
                        NewMemory(
                            kind="summary",
                            text=text,
                            created_seq=state.seq,
                            sim_time=state.sim_time,
                            importance=max([3] + [e.importance for e in own]) / 10,
                            source_events=[e.seq for e in committed.events],
                            participants=sorted(
                                {p for e in own for p in e.participants} - {person.id}
                            ),
                        )
                    ],
                )

            result.summaries.append(f"{state.sim_time:%B %Y}: {summary}")
            result.skipped_minutes += period
            result.periods += 1
        return result
