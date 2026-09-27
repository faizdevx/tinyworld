from dataclasses import dataclass

from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.goal_system import GoalSystem
from WORLD.AI.utility import WORK_LOCATIONS, score_action


@dataclass(frozen=True)
class Decision:
    goals: list[GoalType]
    scores: dict[ActionType, int]
    chosen_action: ActionType

    def debug_text(self, npc) -> str:
        lines = [
            f"{npc.name} decision:",
            "",
        ]

        if self.goals:
            lines.append("Goals:")
            for goal in self.goals:
                lines.append(f"  - {goal.value}")
        else:
            lines.append("Goals:")
            lines.append("  - none")

        lines.append("")
        lines.append("Actions:")

        for action, score in self.scores.items():
            marker = "  ← chosen" if action == self.chosen_action else ""
            lines.append(
                f"  {action.value:<10} {score:>3}{marker}"
            )

        return "\n".join(lines)


class DecisionSystem:
    def __init__(self) -> None:
        self.goal_system = GoalSystem()

    def get_actions(self, npc, world) -> list[ActionType]:
        actions = []

        if npc.food > 0:
            actions.append(ActionType.EAT)

        actions.append(ActionType.SLEEP)

        if npc.location in WORK_LOCATIONS:
            actions.append(ActionType.WORK)

        if (
            npc.money >= world.shop.food_price
            and npc.food == 0
        ):
            actions.append(ActionType.SHOP)

        has_other_npc = any(
            other is not npc
            and other.location == npc.location
            for other in world.npcs
        )

        if has_other_npc:
            actions.append(ActionType.SOCIALIZE)

        return actions

    def decide(self, npc, world) -> Decision:
        goals = self.goal_system.get_goals(
            npc,
            world,
        )

        actions = self.get_actions(
            npc,
            world,
        )

        scores = {
            action: score_action(
                npc=npc,
                action=action,
                world=world,
                goals=goals,
            )
            for action in actions
        }

        chosen_action = max(
            scores,
            key=scores.get,
        )

        return Decision(
            goals=goals,
            scores=scores,
            chosen_action=chosen_action,
        )