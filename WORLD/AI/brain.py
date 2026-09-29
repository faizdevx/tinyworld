from WORLD.AI.plan_executor import PlanExecutor


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
        self.reasoner = reasoner
        self.reflection = reflection

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

        memories = self.retrieve_memories()

        return {
            "goals": goals,
            "selected_goal": selected_goal,
            "memories": memories,
        }

    def retrieve_memories(self):
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

        memories = self.memory_retriever.relevant_memories(
            self.npc,
            topic,
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
        Execute an existing plan when one existed before this
        cognition cycle.

        Otherwise preserve the legacy DecisionSystem behavior.
        """
        if had_active_plan:
            active_plan = getattr(
                self.npc,
                "active_plan",
                None,
            )

            if active_plan is not None:
                if self.plan_executor is None:
                    self.plan_executor = PlanExecutor(
                        self.action_executor
                    )

                return self.plan_executor.execute_current_step(
                    self.npc,
                    active_plan,
                    world,
                )

        return self._legacy_decision(world)

    def reflect(self, world, result):
        """
        Give the optional reflection component the outcome
        of the action.
        """
        if self.reflection is None:
            return None

        return self.reflection.reflect(
            self.npc,
            world,
            result,
        )

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
