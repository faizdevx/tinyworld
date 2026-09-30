from dataclasses import dataclass

from WORLD.AI.action import ActionType
from WORLD.AI.goal import Goal
from WORLD.AI.plans import Plan


@dataclass(frozen=True)
class ReasoningResult:
    goal: Goal | None
    action: ActionType | None
    rationale: str


class Reasoner:
    """
    Deterministic reasoning layer.

    The Reasoner identifies the action currently intended by
    the NPC's cognitive state. It does not execute actions
    and does not mutate world state.
    """

    def __init__(self, decision_system):
        self.decision_system = decision_system

    def reason(
        self,
        npc,
        world,
        *,
        had_active_plan: bool,
        current_goal: Goal | None = None,
        active_plan: Plan | None = None,
    ) -> ReasoningResult:
        if had_active_plan and active_plan is not None:
            action = active_plan.current_action()

            if action is not None:
                return ReasoningResult(
                    goal=current_goal,
                    action=action,
                    rationale="follow_active_plan",
                )

        decision = self.decision_system.decide(
            npc,
            world,
        )

        return ReasoningResult(
            goal=current_goal,
            action=decision.chosen_action,
            rationale="legacy_decision_fallback",
        )
