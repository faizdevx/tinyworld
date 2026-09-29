from WORLD.AI.brain import Brain
from WORLD.AI.goal_system import GoalSystem
from WORLD.AI.memory_retrieval import MemoryRetriever
from WORLD.AI.perception import Perception
from WORLD.AI.planner import Planner
from WORLD.AI.replanner import Replanner
from WORLD.AI.plan_executor import PlanExecutor


class AgentSystem:
    """
    Compatibility adapter around the NPC Brain.

    The Brain owns cognition. AgentSystem only makes sure
    every NPC has a Brain and delegates the update.
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

    def _ensure_brain(self, npc):
        """
        Attach a Brain when one is missing.

        This keeps older tests and lightweight NPC doubles
        compatible with the new architecture.
        """
        if getattr(npc, "brain", None) is None:
            npc.brain = Brain(
                npc=npc,
                perception=self.perception,
                goal_system=self.goal_system,
                planner=self.planner,
                replanner=self.replanner,
                memory_retriever=self.memory_retriever,
                decision_system=self.decision_system,
                action_executor=None,
                plan_executor=self.plan_executor,
            )

        return npc.brain

    def _update_goals(self, npc, world):
        """
        Compatibility shim for callers of the Phase 6 API.
        """
        thought = self._ensure_brain(npc).think(world)
        return thought["goals"]

    def _retrieve_memories(self, npc):
        """
        Compatibility shim for callers of the Phase 6 API.
        """
        return self._ensure_brain(npc).retrieve_memories()

    def _update_plan(self, npc, world):
        """
        Compatibility shim for callers of the Phase 6 API.
        """
        return self._ensure_brain(npc).plan(world)

    def _execute_plan_or_decide(self, npc, world):
        """
        Compatibility shim for callers of the Phase 6 API.
        """
        brain = self._ensure_brain(npc)

        if getattr(brain, "action_executor", None) is None:
            brain.action_executor = world.action_executor

        if getattr(brain, "plan_executor", None) is None:
            brain.plan_executor = PlanExecutor(world.action_executor)

        return brain.act(world, had_active_plan=True)

    def update(self, world):
        """
        Delegate cognition to each NPC's Brain.
        """
        for npc in world.npcs:
            brain = self._ensure_brain(npc)

            if getattr(brain, "action_executor", None) is None:
                brain.action_executor = world.action_executor

            if getattr(brain, "plan_executor", None) is None:
                brain.plan_executor = PlanExecutor(
                    world.action_executor
                )

            brain.update(world)
