class FarmingSystem:
    FOOD_PER_FARMER = 2
    HARVEST_HOUR = 12
    FARM_LOCATION = "Village Farm"

    def update(self, world) -> None:
        if world.clock.hour != self.HARVEST_HOUR:
            return

        farmers = [
            npc
            for npc in world.npcs
            if npc.role == "farmer"
            and npc.location == self.FARM_LOCATION
        ]

        production = len(farmers) * self.FOOD_PER_FARMER

        if production == 0:
            return

        world.food.add(production)