from WORLD.AI.action import ActionType


class NeedsSystem:
    HUNGER_PER_HOUR = 4
    HUNGER_THRESHOLD = 70
    HUNGER_ENERGY_PENALTY = 5

    def update(self, world) -> None:
        self.update_before_decision(world)

        for npc in world.npcs:
            decision = world.decision_system.decide(npc, world)

            if decision.chosen_action == ActionType.EAT:
                world.action_executor.execute(
                    npc,
                    ActionType.EAT,
                    world,
                )

        self.update_after_action(world)

    def update_before_decision(self, world) -> None:
        for npc in world.npcs:
            npc.increase_hunger(self.HUNGER_PER_HOUR)

    def update_after_action(self, world) -> None:
        for npc in world.npcs:
            if npc.hunger >= self.HUNGER_THRESHOLD:
                npc.use_energy(
                    self.HUNGER_ENERGY_PENALTY
                )