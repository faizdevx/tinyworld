class WorkSystem:
    WORK_ENERGY_COST = 5

    WORK_LOCATIONS = {
        "Village Farm",
        "General Store",
    }

    def update(self, world) -> None:
        for npc in world.npcs:
            if npc.location not in self.WORK_LOCATIONS:
                continue

            npc.use_energy(self.WORK_ENERGY_COST)