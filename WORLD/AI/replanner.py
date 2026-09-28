from WORLD.AI.goal import Goal
from WORLD.AI.plans import Plan


class Replanner:
    """
    Creates a new plan when an NPC's active plan
    has been interrupted or is otherwise invalid.
    """

    def __init__(self, goal_system, planner):
        self.goal_system = goal_system
        self.planner = planner

    def needs_replanning(self, npc) -> bool:
        """
        Returns True when the NPC has an interrupted plan.
        """
        plan = getattr(npc, "active_plan", None)

        if plan is None:
            return False

        return plan.is_interrupted()

    def replan(self, npc, world) -> Plan | None:
        """
        Generate a new goal and plan from the NPC's
        current world state.

        Returns the new Plan, or None when no goal exists.
        """
        if not self.needs_replanning(npc):
            return None

        goals = self.goal_system.evaluate_goals(
            npc,
            world,
        )

        current_day = world.clock.day

        selected_goal = self.goal_system.select_highest_priority(
            goals,
            current_day,
        )

        if selected_goal is None:
            npc.current_goal = None
            npc.active_plan = None
            return None

        new_plan = self.planner.create_plan(
            npc,
            selected_goal,
            world,
        )

        npc.current_goal = selected_goal
        npc.active_plan = new_plan

        return new_plan