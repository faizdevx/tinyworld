from WORLD.AI.goal import Goal, GoalType


class GoalSystem:
    HUNGER_THRESHOLD = 70
    ENERGY_THRESHOLD = 30
    MONEY_THRESHOLD = 20

    HUNGER_PRIORITY = 80
    ENERGY_PRIORITY = 80
    MONEY_PRIORITY = 60
    SOCIAL_PRIORITY = 40

    def _get_long_term_goals(self, npc):
        """
        Return the NPC's persistent goals.

        The attribute is created lazily so existing NPCs
        and older tests remain compatible.
        """
        if not hasattr(npc, "long_term_goals"):
            npc.long_term_goals = []

        return npc.long_term_goals

    def add_long_term_goal(self, npc, goal):
        """
        Add a persistent goal to the NPC.
        """
        goals = self._get_long_term_goals(npc)

        if goal not in goals:
            goals.append(goal)

        return goal

    def create_long_term_goal(
        self,
        npc,
        goal_type,
        priority,
        current_day,
        deadline_day=None,
        progress=0.0,
    ):
        """
        Create and store a persistent Goal.
        """
        goal = Goal(
            goal_type=goal_type,
            priority=priority,
            created_day=current_day,
            deadline_day=deadline_day,
            progress=progress,
        )

        self.add_long_term_goal(npc, goal)

        return goal

    def get_long_term_goals(self, npc):
        """
        Return all persistent goals for the NPC.
        """
        return list(self._get_long_term_goals(npc))

    def update_goal_progress(self, goal, progress):
        """
        Update progress while keeping it in the
        valid 0.0 to 1.0 range.
        """
        goal.progress = max(
            0.0,
            min(1.0, progress),
        )

        return goal

    def is_goal_complete(self, goal):
        return goal.progress >= 1.0

    def remove_completed_goal(self, npc, goal):
        """
        Remove a completed long-term goal.
        """
        goals = self._get_long_term_goals(npc)

        if goal in goals and self.is_goal_complete(goal):
            goals.remove(goal)
            return True

        return False

    def get_goals(self, npc, world=None):
        """
        Backward-compatible API.

        Returns the existing GoalType values used by the
        DecisionSystem and older tests.
        """
        goals = []

        if npc.hunger >= self.HUNGER_THRESHOLD:
            goals.append(GoalType.SATISFY_HUNGER)

        if npc.energy <= self.ENERGY_THRESHOLD:
            goals.append(GoalType.RESTORE_ENERGY)

        if npc.money < self.MONEY_THRESHOLD:
            goals.append(GoalType.EARN_MONEY)

        if world is not None:
            nearby_npcs = [
                other
                for other in world.npcs
                if other is not npc
                and other.location == npc.location
            ]

            if nearby_npcs:
                goals.append(GoalType.SOCIALIZE)

        return goals

    def evaluate_goals(self, npc, world=None):
        """
        Phase 6 representation.

        Converts immediate conditions into Goal objects
        containing priority, creation day, deadline and progress.
        """
        goals = []

        if npc.hunger >= self.HUNGER_THRESHOLD:
            goals.append(
                Goal(
                    goal_type=GoalType.SATISFY_HUNGER,
                    priority=self.HUNGER_PRIORITY,
                    created_day=world.clock.day if world else 0,
                )
            )

        if npc.energy <= self.ENERGY_THRESHOLD:
            goals.append(
                Goal(
                    goal_type=GoalType.RESTORE_ENERGY,
                    priority=self.ENERGY_PRIORITY,
                    created_day=world.clock.day if world else 0,
                )
            )

        if npc.money < self.MONEY_THRESHOLD:
            goals.append(
                Goal(
                    goal_type=GoalType.EARN_MONEY,
                    priority=self.MONEY_PRIORITY,
                    created_day=world.clock.day if world else 0,
                )
            )

        if world is not None:
            nearby_npcs = [
                other
                for other in world.npcs
                if other is not npc
                and other.location == npc.location
            ]

            if nearby_npcs:
                goals.append(
                    Goal(
                        goal_type=GoalType.SOCIALIZE,
                        priority=self.SOCIAL_PRIORITY,
                        created_day=world.clock.day,
                    )
                )

        return goals

    def select_highest_priority(self, goals, current_day):
        if not goals:
            return None

        valid_goals = [
            goal
            for goal in goals
            if not self.is_expired(goal, current_day)
        ]

        if not valid_goals:
            return None

        return max(
            valid_goals,
            key=lambda goal: self.effective_priority(
                goal,
                current_day,
            ),
        )

    def is_expired(self, goal, current_day):
        if goal.deadline_day is None:
            return False

        return current_day > goal.deadline_day

    def effective_priority(self, goal, current_day):
        if self.is_expired(goal, current_day):
            return float("-inf")

        priority = goal.priority

        if goal.deadline_day is not None:
            days_remaining = goal.deadline_day - current_day

            if days_remaining <= 1:
                priority += 20
            elif days_remaining <= 3:
                priority += 10

        return priority