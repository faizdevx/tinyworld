from WORLD.AI.goal_system import GoalSystem
from WORLD.AI.memory_retrieval import MemoryRetriever
from WORLD.AI.perception import Perception
from WORLD.AI.planner import Planner
from WORLD.AI.replanner import Replanner


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
        Evaluate current needs and keep the highest-priority
        immediate goal available to the agent.
        """
        goals = self.goal_system.evaluate_goals(
            npc,
            world,
        )

        current_day = world.clock.day

        selected_goal = self.goal_system.select_highest_priority(
            goals,
            current_day,
        )

        if selected_goal is not None:
            npc.current_goal = selected_goal

        return goals

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

    def update(self, world):
        """
        Run one cognition cycle for every NPC.

        Pipeline:

        Perception
            ↓
        Beliefs
            ↓
        Goals
            ↓
        Plan / Replan
            ↓
        Decision
            ↓
        Action
        """
        for npc in world.npcs:
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

            decision = self.decision_system.decide(
                npc,
                world,
            )

            world.action_executor.execute(
                npc,
                decision.chosen_action,
                world,
            )