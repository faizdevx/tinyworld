"""One pass of intents through propose → resolve → commit → perceive."""

from dataclasses import dataclass, field

from tinyworld.core.events import Event, Intent, Outcome
from tinyworld.core.session import WorldSession
from tinyworld.gm.master import GameMaster, feedback
from tinyworld.gm.perception import Observation, perceive
from tinyworld.llm.types import CallContext


@dataclass
class StepResult:
    outcomes: list[Outcome] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)


async def apply_intents(
    session: WorldSession,
    gm: GameMaster,
    intents: list[Intent],
    context: CallContext | None = None,
) -> StepResult:
    """Resolve intents against the session's state and commit what happens."""
    context = context or CallContext(session.branch_id, session.state.seq)
    before = session.state
    resolution = await gm.resolve(before, intents, context)
    committed = session.commit(resolution.drafts, atomic=False, observe=perceive)

    outcomes = list(resolution.outcomes)
    # A draft can still be refused at commit when two independently
    # adjudicated outcomes turn out to collide.
    for draft, reason in committed.rejected:
        position = next(i for i, d in enumerate(resolution.drafts) if d is draft)
        index = resolution.draft_outcome[position]
        outcomes[index] = outcomes[index].model_copy(
            update={"status": "failed", "effects": [], "reason": reason}
        )

    observations = [o for batch in committed.observed for o in batch]
    for outcome in outcomes:
        note = feedback(before, outcome)
        if note is None:
            continue
        # The actor always learns why their own attempt went wrong.
        observations.append(
            Observation(
                observer=outcome.intent.agent,
                event_seq=session.state.seq,
                sim_time=session.state.sim_time,
                mode="self",
                confidence=1.0,
                text=note,
                location=before.entities[outcome.intent.agent].location
                if outcome.intent.agent in before.entities
                else None,
                actor=outcome.intent.agent,
            )
        )
    return StepResult(outcomes, committed.events, observations)
