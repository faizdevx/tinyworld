from WORLD.world import World


class Simulation:

    def __init__(self, world: World) -> None:
        self.world = world

    def tick(self) -> None:
        hour = self.world.clock.hour

        # 1. Apply NPC schedules.
        for npc in self.world.npcs:
            self.world.schedule_system.update_npc(
                npc,
                hour,
            )

        # 2. Farmers produce food.
        self.world.farming_system.update(
            self.world
        )

        # 3. Move village food into shop inventory.
        self.world.restocking_system.update(
            self.world
        )

        # 4. NPCs buy food.
        self.world.shopping_system.update(
            self.world
        )

        # 5. NPCs consume their own food.
        self.world.needs_system.update(
            self.world
        )

        # 6. Advance simulation time.
        self.world.clock.tick()

    def run(self, ticks: int) -> None:
        if ticks < 0:
            raise ValueError("Ticks cannot be negative.")

        for _ in range(ticks):
            self.tick()