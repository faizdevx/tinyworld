"""The Game Master: intents in, outcomes and event drafts out."""

import asyncio
from dataclasses import dataclass, field

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft, Intent, Outcome
from tinyworld.core.reducers import EffectError, apply_effect
from tinyworld.core.registry import REGISTRY, AttrRegistry
from tinyworld.core.rng import seeded
from tinyworld.core.state import WorldState
from tinyworld.gm import conflicts, rules
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.context import name_of
from tinyworld.llm.types import CallContext


@dataclass
class Resolution:
    outcomes: list[Outcome] = field(default_factory=list)
    drafts: list[EventDraft] = field(default_factory=list)
    # Index into ``outcomes`` for each draft, so feedback can be matched up.
    draft_outcome: list[int] = field(default_factory=list)


def outcome_draft(state: WorldState, outcome: Outcome) -> EventDraft | None:
    """The event an outcome leaves behind, if it leaves one.

    An impossible attempt never happened, so it produces no event. A failed
    attempt was visible to onlookers and does.
    """
    if outcome.status == "impossible":
        return None
    intent = outcome.intent
    agent = state.entities[intent.agent]
    narration = outcome.narration
    if not narration:
        if outcome.status == "failed":
            narration = f"{agent.name} tries to {intent.verb.value} but fails."
        else:
            narration = f"{agent.name} does something."
    effects = list(outcome.effects)
    from tinyworld.world import walking

    if intent.verb.value != "move":
        effects += walking.stop_effects(agent)
    only_speech = bool(outcome.effects) and all(
        isinstance(effect, fx.Utter) for effect in outcome.effects
    )
    return EventDraft(
        kind="utterance" if only_speech else "action",
        actor=intent.agent,
        location=agent.location,
        effects=effects,
        narration=narration,
        loud=outcome.loud,
        trace_id=outcome.trace_id,
    )


class GameMaster:
    def __init__(
        self,
        adjudicator: Adjudicator | None = None,
        *,
        registry: AttrRegistry = REGISTRY,
        seed: str = "",
    ) -> None:
        self.adjudicator = adjudicator
        self.registry = registry
        self.seed = seed

    def _apply(self, working: WorldState, outcome: Outcome, base: WorldState | None = None, applied: list | None = None) -> Outcome:
        """Apply a rule-resolved outcome to the working state, or fail it.

        Copying the whole world before every outcome is the dearest thing a tick does, so a failure
        is undone the other way round: start again from ``base`` and re-apply what had succeeded.
        """
        done = 0
        try:
            for effect in outcome.effects:
                apply_effect(working, effect, self.registry)
                done += 1
        except EffectError as exc:
            if base is None:
                raise
            fresh = base.model_copy(deep=True)
            for earlier in applied or []:
                apply_effect(fresh, earlier, self.registry)
            # Restore in place: later intents keep using the same object.
            for name in type(working).model_fields:
                setattr(working, name, getattr(fresh, name))
            return outcome.model_copy(
                update={"status": "impossible", "effects": [], "reason": str(exc)}
            )
        if applied is not None:
            applied.extend(outcome.effects)
        return outcome

    async def resolve(
        self,
        state: WorldState,
        intents: list[Intent],
        context: CallContext,
    ) -> Resolution:
        """Decide what happens to a tick's worth of intents.

        Rule-resolved intents are applied one after another in a seeded random
        order, so two people reaching for the last loaf are settled without a
        model. The rest are grouped by what they contend for and adjudicated,
        independent groups concurrently.
        """
        order = list(range(len(intents)))
        seeded(self.seed, context.tick_seq).shuffle(order)

        working = state.model_copy(deep=True)
        applied: list = []
        outcomes: dict[int, Outcome] = {}
        pending: dict[int, list] = {}

        for index in order:
            intent = intents[index]
            verdict = rules.check(working, intent)
            if verdict.status == "resolved":
                outcomes[index] = self._apply(working, verdict.outcome, state, applied)
            elif verdict.status == "impossible":
                outcomes[index] = verdict.outcome
            else:
                pending[index] = verdict.preset or []

        if pending:
            indices = sorted(pending)
            if self.adjudicator is None:
                for index in indices:
                    outcomes[index] = Outcome(
                        intent=intents[index],
                        status="failed",
                        reason="no Game Master model is configured",
                    )
            else:
                groups = conflicts.group(working, [intents[i] for i in indices])
                position = {id(intents[i]): i for i in indices}

                async def settle(members: list[Intent]) -> list[tuple[int, Outcome]]:
                    if len(members) == 1:
                        index = position[id(members[0])]
                        outcome = await self.adjudicator.adjudicate(
                            working, members[0], context, preset=pending[index]
                        )
                        return [(index, outcome)]
                    presets = {
                        m.agent: pending[position[id(m)]] for m in members
                    }
                    settled = await self.adjudicator.adjudicate_group(
                        working, members, context, presets=presets
                    )
                    return [(position[id(m)], o) for m, o in zip(members, settled)]

                for batch in await asyncio.gather(*(settle(g) for g in groups)):
                    outcomes.update(batch)

        resolution = Resolution()
        resolution.outcomes = [outcomes[i] for i in range(len(intents))]
        # Drafts follow resolution order so each applies to the state the
        # rules saw: rule-resolved ones first, adjudicated ones after.
        emit = [i for i in order if i not in pending] + sorted(pending)
        for index in emit:
            draft = outcome_draft(state, outcomes[index])
            if draft is not None:
                resolution.drafts.append(draft)
                resolution.draft_outcome.append(index)
        return resolution


def feedback(state: WorldState, outcome: Outcome) -> str | None:
    """What the actor privately learns when an attempt did not simply succeed."""
    if outcome.status == "success":
        return None
    agent_name = name_of(state, outcome.intent.agent)
    what = outcome.intent.text or outcome.intent.verb.value
    if outcome.status == "impossible":
        return f"{agent_name} could not do this ({what}): {outcome.reason}"
    if outcome.status == "failed":
        return f"{agent_name} tried ({what}) and it did not work: {outcome.reason or outcome.narration}"
    return f"{agent_name} only partly managed ({what}): {outcome.reason or outcome.narration}"
