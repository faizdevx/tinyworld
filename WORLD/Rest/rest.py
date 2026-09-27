class RestSystem:
    SLEEP_START = 22
    SLEEP_END = 6
    ENERGY_PER_HOUR = 15

    def update(self, world) -> None:
        hour = world.clock.hour

        sleeping_time = (
            hour >= self.SLEEP_START
            or hour < self.SLEEP_END
        )

        if not sleeping_time:
            return

        for npc in world.npcs:
            if npc.location != npc.home:
                continue

            npc.restore_energy(self.ENERGY_PER_HOUR)