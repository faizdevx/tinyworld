from WORLD.world import World


class Simulation:

    def __init__(self, world: World) -> None:
        self.world = world

    def tick(self) -> None:
        hour = self.world.clock.hour

        # 1. Move NPCs according to schedules.
        for npc in self.world.npcs:
            self.world.schedule_system.update_npc(npc, hour)

        # 2. Process social interactions.
        self.world.social_system.update(self.world)

        # 3. Working costs energy.
        self.world.work_system.update(self.world)

        # 4. Farmers produce food.
        self.world.farming_system.update(self.world)

        # 5. Move village food to shop.
        self.world.restocking_system.update(self.world)

        # 6. NPCs buy food.
        self.world.shopping_system.update(self.world)

        # 7. Hunger and eating.
        self.world.needs_system.update(self.world)

        # 8. Sleeping restores energy.
        self.world.rest_system.update(self.world)

        # 9. Move to next hour.
        self.world.clock.tick()

    def run(self, ticks: int) -> None:
        if ticks < 0:
            raise ValueError(
                "Ticks cannot be negative."
            )

        for _ in range(ticks):
            self.tick()
