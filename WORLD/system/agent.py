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
    concrete actions when there is no active executable plan.
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
        Update the NPC's beliefs from current perception.
        """
        observations = self.perception.observe(
            npc,
            world,
        )

        npc.beliefs = observations

        return observations

    def _update_goals(self, npc, world):
        """
        Evaluate immediate needs and persistent long-term goals.
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

        selected_goal = self.goal_system.select_highest_priority(
            all_goals,
            world.clock.day,
        )

        npc.current_goal = selected_goal

        return all_goals

    def _retrieve_memories(self, npc):
        """
        Retrieve memories relevant to the current goal.
        """
        current_goal = getattr(
            npc,
            "current_goal",
            None,
        )

        if current_goal is None:
            npc.relevant_memories = []
            return []

        topic = current_goal.goal_type.value

        memories = self.memory_retriever.relevant_memories(
            npc,
            topic,
        )

        npc.relevant_memories = memories

        return memories

    def _update_plan(self, npc, world):
        """
        Create a new plan when none exists.

        Replace an interrupted plan through the Replanner.
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
        Execute an active plan through PlanExecutor.

        PlanExecutor owns:
        - interruption
        - precondition checking
        - action execution
        - plan advancement

        DecisionSystem is used only when there is no active plan.
        """
        active_plan = getattr(
            npc,
            "active_plan",
            None,
        )

        if active_plan is not None:
            if self.plan_executor is None:
                self.plan_executor = PlanExecutor(
                    world.action_executor,
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

        Existing plans are executed through PlanExecutor.
        NPCs without an existing plan retain the legacy
        DecisionSystem behavior.
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

            self._retrieve_memories(
                npc,
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