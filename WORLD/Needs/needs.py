from WORLD.AI.action import ActionType


class NeedsSystem:
    HUNGER_PER_HOUR = 4

    HUNGER_THRESHOLD = 70
    HUNGER_ENERGY_PENALTY = 5

    def update(self, world) -> None:
        for npc in world.npcs:

            # Hunger is a passive state change that happens every hour.
            npc.increase_hunger(self.HUNGER_PER_HOUR)

            # Eating is now a decision, not a fixed clock event.
            decision = world.decision_system.decide(npc, world)

            if decision.chosen_action == ActionType.EAT:
                ate = world.action_executor.execute(
                    npc,
                    ActionType.EAT,
                    world,
                )

                if ate:
                    continue

            # If the NPC is still very hungry and could not eat,
            # hunger causes an energy penalty.
            if npc.hunger >= self.HUNGER_THRESHOLD:
                npc.use_energy(self.HUNGER_ENERGY_PENALTY)