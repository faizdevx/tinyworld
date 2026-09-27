class NeedsSystem:
    CONSUMPTION_HOUR = 20
    FOOD_PER_NPC = 1
    ENERGY_GAIN = 20

    def update(self, world) -> None:
        # NPCs eat at 20:00.
        if world.clock.hour != self.CONSUMPTION_HOUR:
            return

        for npc in world.npcs:

            # NPC must have food in their own inventory.
            if not npc.consume_food(self.FOOD_PER_NPC):
                continue

            # Eating restores energy.
            npc.restore_energy(self.ENERGY_GAIN)