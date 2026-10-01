from WORLD.AI.experience_influence import ExperienceInfluence
from WORLD.AI.knowledge import KnowledgeBase
from WORLD.AI.knowledge_extractor import KnowledgeExtractor
from WORLD.AI.plan_executor import PlanExecutor
from WORLD.AI.reasoner import Reasoner
from WORLD.AI.reflection_scheduler import ReflectionScheduler
from WORLD.AI.social_memory import SocialMemoryStore


class Brain:
    """
    Unified deterministic cognition coordinator for one NPC.

    The Brain owns the NPC cognition lifecycle while the
    underlying systems remain independent components.
    """

    def __init__(
        self,
        npc,
        perception,
        goal_system,
        planner,
        replanner,
        memory_retriever,
        decision_system,
        action_executor,
        plan_executor=None,
        reasoner=None,
        reflection=None,
        experience_reflector=None,
        knowledge_extractor=None,
        reflection_scheduler=None,
        experience_influence=None,
    ):
        self.npc = npc
        self.perception = perception
        self.goal_system = goal_system
        self.planner = planner
        self.replanner = replanner
        self.memory_retriever = memory_retriever
        self.decision_system = decision_system
        self.action_executor = action_executor
        self.plan_executor = plan_executor
        self.reasoner = (
            reasoner
            if reasoner is not None
            else Reasoner(decision_system)
        )
        self.reflection = reflection
        self.experience_reflector = experience_reflector
        self.knowledge_extractor = (
            knowledge_extractor
            if knowledge_extractor is not None
            else KnowledgeExtractor()
        )
        self.reflection_scheduler = (
            reflection_scheduler
            if reflection_scheduler is not None
            else ReflectionScheduler()
        )
        self.experience_influence = experience_influence
        self.last_reasoning = None
        self.last_reflection = None
        self.last_experience_reflection = None

    def observe(self, world):
        """
        Observe the current world state and update beliefs.
        """
        observations = self.perception.observe(
            self.npc,
            world,
        )

        self.npc.beliefs = observations

        return observations

    def think(self, world):
        """
        Evaluate immediate needs and persistent goals,
        then retrieve memories relevant to the selected goal.
        """
        immediate_goals = self.goal_system.evaluate_goals(
            self.npc,
            world,
        )

        long_term_goals = [
            goal
            for goal in self.goal_system.get_long_term_goals(
                self.npc
            )
            if not self.goal_system.is_goal_complete(goal)
        ]

        goals = immediate_goals + long_term_goals

        selected_goal = self.goal_system.select_highest_priority(
            goals,
            world.clock.day,
        )

        self.npc.current_goal = selected_goal

        memories = self.retrieve_memories(world)

        return {
            "goals": goals,
            "selected_goal": selected_goal,
            "memories": memories,
        }

    def retrieve_memories(self, world=None):
        """
        Retrieve memories relevant to the current goal.
        """
        current_goal = getattr(
            self.npc,
            "current_goal",
            None,
        )

        if current_goal is None:
            self.npc.relevant_memories = []
            return []

        topic = current_goal.goal_type.value

        current_timestamp = None
        if world is not None:
            clock = getattr(world, "clock", None)
            day = getattr(clock, "day", None)
            hour = getattr(clock, "hour", None)

            if day is not None and hour is not None:
                current_timestamp = (
                    (day - 1) * 24
                    + hour
                )

        memories = self.memory_retriever.retrieve(
            self.npc,
            topic,
            limit=5,
            min_importance=0.0,
            current_timestamp=current_timestamp,
        )

        self.npc.relevant_memories = memories

        return memories

    def plan(self, world):
        """
        Continue an existing plan, replan an interrupted plan,
        or create a new plan for the current goal.
        """
        active_plan = getattr(
            self.npc,
            "active_plan",
            None,
        )

        if active_plan is not None:
            if self.replanner.needs_replanning(
                self.npc
            ):
                return self.replanner.replan(
                    self.npc,
                    world,
                )

            return active_plan

        current_goal = getattr(
            self.npc,
            "current_goal",
            None,
        )

        if current_goal is None:
            return None

        self.npc.active_plan = self.planner.create_plan(
            self.npc,
            current_goal,
            world,
        )

        return self.npc.active_plan

    def act(self, world, had_active_plan=False):
        """
        Execute the action selected by the current reasoning state.

        Existing plans still go through PlanExecutor. NPCs without a
        plan from the start of the cycle retain the legacy behavior.
        """
        active_plan = getattr(
            self.npc,
            "active_plan",
            None,
        )

        reasoning = self.reasoner.reason(
            self.npc,
            world,
            had_active_plan=had_active_plan,
            current_goal=getattr(
                self.npc,
                "current_goal",
                None,
            ),
            active_plan=active_plan,
        )

        self.last_reasoning = reasoning

        if had_active_plan and active_plan is not None:
            if self.plan_executor is None:
                self.plan_executor = PlanExecutor(
                    self.action_executor
                )

            return self.plan_executor.execute_current_step(
                self.npc,
                active_plan,
                world,
            )

        if reasoning.action is None:
            return False

        return self.action_executor.execute(
            self.npc,
            reasoning.action,
            world,
        )

    def reflect(self, world, result):
        """
        Give the optional reflection component the outcome
        of the action.
        """
        if self.reflection is None:
            return None

        reflection = self.reflection.reflect(
            self.npc,
            world,
            result,
            reasoning=self.last_reasoning,
        )

        self.last_reflection = reflection

        return reflection

    def reflect_on_memory(
        self,
        memory,
        current_goal=None,
    ):
        if self.experience_reflector is None:
            return None

        reflection = self.experience_reflector.reflect(
            self.npc,
            memory,
            current_goal=current_goal,
        )

        self.last_experience_reflection = reflection

        return reflection

    def learn_from_reflection(self, reflection):
        if reflection is None:
            return None

        knowledge = self.knowledge_extractor.extract(
            self.npc,
            reflection,
        )

        if knowledge is None:
            return None

        if not hasattr(self.npc, "knowledge"):
            self.npc.knowledge = KnowledgeBase()

        stored = self.npc.knowledge.add(
            subject=knowledge.subject,
            predicate=knowledge.predicate,
            value=knowledge.value,
            confidence=knowledge.confidence,
        )

        return stored

    def should_reflect_on_memory(self, memory):
        if self.reflection_scheduler is None:
            return False

        decision = self.reflection_scheduler.should_reflect(memory)
        return decision.should_reflect

    def scheduled_reflect(self, memory, current_goal=None):
        if self.reflection_scheduler is None:
            return None

        decision = self.reflection_scheduler.should_reflect(memory)
        if not decision.should_reflect:
            return None

        return self.reflect_on_memory(memory, current_goal=current_goal)

    def get_knowledge_about(self, person: str):
        if not hasattr(self.npc, "knowledge"):
            self.npc.knowledge = KnowledgeBase()
        return self.npc.knowledge.for_subject(person)

    def experience_influences(self, person: str):
        if self.experience_influence is None:
            return []
        knowledge = self.get_knowledge_about(person)
        return self.experience_influence.influence(
            knowledge,
            target=person,
        )

    def retrieve_social_context(self, person: str, *, memory_limit: int = 5):
        if not hasattr(self.npc, "social_memory"):
            self.npc.social_memory = SocialMemoryStore()
        if not hasattr(self.npc, "knowledge"):
            self.npc.knowledge = KnowledgeBase()

        memories = self.npc.social_memory.for_person(
            person,
            limit=memory_limit,
        )
        knowledge = self.npc.knowledge.for_subject(person)

        return {
            "person": person,
            "memories": memories,
            "knowledge": knowledge,
            "relationship": getattr(self.npc, "relationships", {}).get(person),
        }

    def update(self, world):
        """
        Execute one complete cognition lifecycle.
        """
        active_plan_before_update = getattr(
            self.npc,
            "active_plan",
            None,
        )

        had_active_plan = (
            active_plan_before_update is not None
            and not active_plan_before_update.is_complete()
        )

        self.observe(world)

        self.think(world)

        self.plan(world)

        result = self.act(
            world,
            had_active_plan=had_active_plan,
        )

        self.reflect(
            world,
            result,
        )

        return result

    def _legacy_decision(self, world):
        """
        Preserve the existing deterministic DecisionSystem
        behavior for NPCs without an active plan at the start
        of the cognition cycle.
        """
        decision = self.decision_system.decide(
            self.npc,
            world,
        )

        return self.action_executor.execute(
            self.npc,
            decision.chosen_action,
            world,
        )
