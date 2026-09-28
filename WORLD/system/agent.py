from WORLD.AI.goal_system import GoalSystem
from WORLD.AI.memory_retrieval import MemoryRetriever
from WORLD.AI.perception import Perception
from WORLD.AI.planner import Planner
from WORLD.AI.replanner import Replanner

from WORLD.AI.plan_executor import PlanExecutor
class AgentSystem:
    """
    Coordinates the Phase 6 cognition pipeline.

    The existing DecisionSystem remains responsible for choosing
    the concrete action, while this class coordinates perception,
    goals, plans, and replanning around it.
    """

    def __init__(
        self,
        decision_system,
        perception=None,
        goal_system=None,
        planner=None,
        replanner=None,
        memory_retriever=None,
        plan_executor=None,
    ):
        self.decision_system = decision_system

        self.perception = (
            perception
            if perception is not None
            else Perception()
        )

        self.goal_system = (
            goal_system
            if goal_system is not None
            else GoalSystem()
        )

        self.planner = (
            planner
            if planner is not None
            else Planner()
        )

        self.replanner = (
            replanner
            if replanner is not None
            else Replanner(
                goal_system=self.goal_system,
                planner=self.planner,
            )
        )

        self.memory_retriever = (
            memory_retriever
            if memory_retriever is not None
            else MemoryRetriever()
        )

        self.plan_executor = plan_executor

    def _update_beliefs(self, npc, world):
        """
        Phase 6.14 currently uses perfect perception.

        Store the latest observations directly on the NPC.
        """
        observations = self.perception.observe(
            npc,
            world,
        )

        npc.beliefs = observations

        return observations

    def _update_goals(self, npc, world):
        """
        Evaluate immediate needs together with persistent
        long-term goals, then select the highest-priority
        active goal.

        Urgent needs and long-term objectives compete through
        the same priority-selection mechanism.
        """
        immediate_goals = self.goal_system.evaluate_goals(
            npc,
            world,
        )

        long_term_goals = [
            goal
            for goal in self.goal_system.get_long_term_goals(npc)
            if not self.goal_system.is_goal_complete(goal)
        ]

        all_goals = immediate_goals + long_term_goals

        current_day = world.clock.day

        selected_goal = self.goal_system.select_highest_priority(
            all_goals,
            current_day,
        )

        if selected_goal is not None:
            npc.current_goal = selected_goal
        else:
            npc.current_goal = None

        return all_goals

    def _update_plan(self, npc, world):
        """
        Replan an interrupted plan.

        When no plan exists but a current goal exists, create
        the initial plan.
        """
        active_plan = getattr(
            npc,
            "active_plan",
            None,
        )

        if active_plan is not None:
            if self.replanner.needs_replanning(npc):
                return self.replanner.replan(
                    npc,
                    world,
                )

            return active_plan

        current_goal = getattr(
            npc,
            "current_goal",
            None,
        )

        if current_goal is None:
            return None

        npc.active_plan = self.planner.create_plan(
            npc,
            current_goal,
            world,
        )

        return npc.active_plan

    def _execute_plan_or_decide(self, npc, world):
        """
        Execute the active plan when one exists.

        PlanExecutor owns plan interruption and execution.
        DecisionSystem is only used when there is no active plan
        or the plan has been completed.
        """
        active_plan = getattr(
            npc,
            "active_plan",
            None,
        )

        if active_plan is not None:
            if self.plan_executor is None:
                self.plan_executor = PlanExecutor(
                    world.action_executor
                )

            return self.plan_executor.execute_current_step(
                npc,
                active_plan,
                world,
            )

        decision = self.decision_system.decide(
            npc,
            world,
        )

        return world.action_executor.execute(
            npc,
            decision.chosen_action,
            world,
        )

    def update(self, world):
        """
        Run one cognition cycle for every NPC.

        Existing active plans are executed through PlanExecutor.
        NPCs without an existing active plan retain the legacy
        DecisionSystem behavior.

        Pipeline:

        Perception
            ↓
        Beliefs
            ↓
        Goals
            ↓
        Plan / Replan
            ↓
        PlanExecutor OR DecisionSystem
            ↓
        Action
        """
        for npc in world.npcs:
            active_plan_before_update = getattr(
                npc,
                "active_plan",
                None,
            )

            had_active_plan = (
                active_plan_before_update is not None
                and not active_plan_before_update.is_complete()
            )

            self._update_beliefs(
                npc,
                world,
            )

            self._update_goals(
                npc,
                world,
            )

            self._update_plan(
                npc,
                world,
            )

            if had_active_plan:
                self._execute_plan_or_decide(
                    npc,
                    world,
                )
            else:
                decision = self.decision_system.decide(
                    npc,
                    world,
                )

                world.action_executor.execute(
                    npc,
                    decision.chosen_action,
                    world,
                )