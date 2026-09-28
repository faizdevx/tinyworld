from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan


class Planner:
    def create_plan(self, npc, goal, world):
        goal_type = goal.goal_type

        if goal_type == GoalType.EARN_MONEY:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "go_to_work",
                    "work",
                ],
            )

        if goal_type == GoalType.SURVIVE:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "find_food",
                    "obtain_food",
                    "eat",
                ],
            )

        if goal_type == GoalType.SATISFY_HUNGER:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "obtain_food",
                    "eat",
                ],
            )

        if goal_type == GoalType.RESTORE_ENERGY:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "go_home",
                    "sleep",
                ],
            )

        if goal_type == GoalType.SOCIALIZE:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "socialize",
                ],
            )

        if goal_type == GoalType.BUILD_RELATIONSHIP:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "socialize",
                ],
            )

        if goal_type == GoalType.HELP_FAMILY:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "find_family",
                    "help_family",
                ],
            )

        if goal_type == GoalType.MAINTAIN_HOME:
            return Plan(
                goal_type=goal_type,
                actions=[
                    "go_home",
                    "maintain_home",
                ],
            )

        return Plan(
            goal_type=goal_type,
            actions=[],
        )