from WORLD.AI.goal import GoalType


class GoalSystem:
    HUNGER_THRESHOLD = 70
    LOW_ENERGY_THRESHOLD = 30
    LOW_MONEY_THRESHOLD = 20

    def get_goals(self, npc, world=None) -> list[GoalType]:
        goals = []

        if npc.hunger >= self.HUNGER_THRESHOLD:
            goals.append(GoalType.SATISFY_HUNGER)

        if npc.energy <= self.LOW_ENERGY_THRESHOLD:
            goals.append(GoalType.RESTORE_ENERGY)

        if npc.money < self.LOW_MONEY_THRESHOLD:
            goals.append(GoalType.EARN_MONEY)

        if world is not None:
            has_companion = any(
                other is not npc
                and other.location == npc.location
                for other in world.npcs
            )

            if has_companion:
                goals.append(GoalType.SOCIALIZE)

        return goals