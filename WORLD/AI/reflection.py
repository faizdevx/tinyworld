from dataclasses import dataclass

from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.reasoner import ReasoningResult


@dataclass(frozen=True)
class ReflectionResult:
    action: ActionType | None
    goal_type: GoalType | None
    success: bool
    lesson: str


class Reflection:
    """
    Deterministic post-action reflection.

    Reflection interprets the result of an attempted action.
    It does not execute actions or mutate world state.
    """

    def reflect(
        self,
        npc,
        world,
        result: bool,
        reasoning: ReasoningResult | None = None,
    ) -> ReflectionResult:
        action = None
        goal_type = None

        if reasoning is not None:
            action = reasoning.action

            if reasoning.goal is not None:
                goal_type = reasoning.goal.goal_type

        if action is None:
            lesson = "no_action_attempted"
        elif result:
            lesson = "action_succeeded"
        else:
            lesson = "action_failed"

        return ReflectionResult(
            action=action,
            goal_type=goal_type,
            success=result,
            lesson=lesson,
        )
