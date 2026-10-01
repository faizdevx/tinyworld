from dataclasses import dataclass

from WORLD.AI.action import ActionType
from WORLD.AI.knowledge import Knowledge


@dataclass(frozen=True)
class BehaviorInfluence:
    """
    Deterministic behavioral influence derived from knowledge.
    This layer does not execute actions and does not mutate state.
    """

    action: ActionType
    modifier: int
    reason: str


class ExperienceInfluence:
    """
    Converts learned knowledge into small deterministic action
    score modifiers. This is intentionally narrow.
    """

    HELPFUL_PERSON_BONUS = 20
    UNHELPFUL_PERSON_PENALTY = -20

    def influence(
        self,
        knowledge: list[Knowledge],
        *,
        target: str | None = None,
    ) -> list[BehaviorInfluence]:
        influences: list[BehaviorInfluence] = []

        for fact in knowledge:
            if target is not None and fact.subject != target:
                continue
            if fact.predicate != "provides_help":
                continue

            if fact.value is True:
                modifier = self.HELPFUL_PERSON_BONUS
                reason = "person_known_to_help"
            elif fact.value is False:
                modifier = self.UNHELPFUL_PERSON_PENALTY
                reason = "person_known_to_refuse_help"
            else:
                continue

            influences.append(
                BehaviorInfluence(
                    action=ActionType.SOCIALIZE,
                    modifier=modifier,
                    reason=reason,
                )
            )

        return influences
