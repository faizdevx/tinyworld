class NeedsSystem:
    HUNGER_PER_HOUR = 4

    EAT_HOUR = 20

    FOOD_PER_MEAL = 1
    HUNGER_REDUCTION = 40
    ENERGY_GAIN = 20

    HUNGER_THRESHOLD = 70
    HUNGER_ENERGY_PENALTY = 5

    def update(self, world) -> None:
        hour = world.clock.hour

        for npc in world.npcs:

            # Hunger naturally increases over time.
            npc.increase_hunger(self.HUNGER_PER_HOUR)

            # NPCs eat at 20:00.
            if hour == self.EAT_HOUR:
                ate = npc.eat(
                    food_amount=self.FOOD_PER_MEAL,
                    hunger_reduction=self.HUNGER_REDUCTION,
                    energy_gain=self.ENERGY_GAIN,
                )

                if ate:
                    continue

            # Severe hunger causes an energy penalty.
            if npc.hunger >= self.HUNGER_THRESHOLD:
                npc.use_energy(
                    self.HUNGER_ENERGY_PENALTY
                )