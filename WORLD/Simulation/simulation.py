from WORLD.world import World


class Simulation:
    def __init__(self, world: World) -> None:
        self.world = world

    def tick(self) -> None:
        hour = self.world.clock.hour

        # 1. Follow the normal schedule.
        for npc in self.world.npcs:
            self.world.schedule_system.update_npc(
                npc,
                hour,
            )

        # 2. Passive hunger update.
        self.world.needs_system.update_before_decision(
            self.world
        )

        # 3. Move village food to the shop when due.
        self.world.restocking_system.update(
            self.world
        )

        # 4. Each NPC makes exactly ONE decision.
        self.world.agent_system.update(
            self.world
        )

        # 5. Farming uses the result of the NPC action.
        self.world.farming_system.update(
            self.world
        )

        # 6. Apply consequences of remaining hunger.
        self.world.needs_system.update_after_action(
            self.world
        )

        # 7. Advance time.
        self.world.clock.tick()

    def run(self, ticks: int) -> None:
        if ticks < 0:
            raise ValueError(
                "ticks cannot be negative"
            )

        for _ in range(ticks):
            self.tick()