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


class DecisionSystem:
    def __init__(self) -> None:
        self.goal_system = GoalSystem()

    def get_actions(self, npc, world) -> list[ActionType]:
        actions = []

        if npc.food > 0:
            actions.append(ActionType.EAT)

        # Sleep is always a possible action.
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
        goals = self.goal_system.get_goals(npc,world)
        actions = self.get_actions(npc, world)

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