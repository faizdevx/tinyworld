from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan


class Planner:
    def create_plan(self, npc, goal, world):
        goal_type = goal.goal_type

        if goal_type == GoalType.EARN_MONEY:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.GO_TO_WORK,
                    ActionType.WORK,
                ],
            )

        if goal_type == GoalType.SURVIVE:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.FIND_FOOD,
                    ActionType.OBTAIN_FOOD,
                    ActionType.EAT,
                ],
            )

        if goal_type == GoalType.SATISFY_HUNGER:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.OBTAIN_FOOD,
                    ActionType.EAT,
                ],
            )

        if goal_type == GoalType.RESTORE_ENERGY:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.GO_HOME,
                    ActionType.SLEEP,
                ],
            )

        if goal_type == GoalType.SOCIALIZE:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.SOCIALIZE,
                ],
            )

        if goal_type == GoalType.BUILD_RELATIONSHIP:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.SOCIALIZE,
                ],
            )

        if goal_type == GoalType.HELP_FAMILY:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.FIND_FAMILY,
                    ActionType.HELP_FAMILY,
                ],
            )

        if goal_type == GoalType.MAINTAIN_HOME:
            return Plan(
                goal_type=goal_type,
                actions=[
                    ActionType.GO_HOME,
                    ActionType.MAINTAIN_HOME,
                ],
            )

        return Plan(
            goal_type=goal_type,
            actions=[],
        )
