from WORLD.AI.action import ActionType
from WORLD.Economy.trading import buy_food
from WORLD.Social.social import SocialSystem


class ActionExecutor:
    WORK_ENERGY_COST = 5
    SLEEP_ENERGY_GAIN = 15
    WORK_LOCATIONS = {
        "Village Farm",
        "General Store",
    }

    def execute(self, npc, action: ActionType, world) -> bool:

        if action == ActionType.EAT:
            return npc.eat()

        if action == ActionType.SLEEP:
            return self._sleep(npc)

        if action == ActionType.WORK:
            return self._work(npc)

        if action == ActionType.SHOP:
            return self._shop(npc, world)

        if action == ActionType.SOCIALIZE:
            return self._socialize(npc, world)

        return False

    def _sleep(self, npc) -> bool:
        if npc.location != npc.home:
            npc.move_to(npc.home)
            
        old_energy = npc.energy
        npc.restore_energy(self.SLEEP_ENERGY_GAIN)

        return npc.energy > old_energy

    def _work(self, npc) -> bool:
        if npc.location not in self.WORK_LOCATIONS:
            return False

        old_energy = npc.energy
        npc.use_energy(self.WORK_ENERGY_COST)

        return npc.energy < old_energy

    def _shop(self, npc, world) -> bool:
        npc.move_to(world.shop.name)

        return buy_food(npc, world.shop)

    def _socialize(self, npc, world) -> bool:
        social_system = SocialSystem()

        for other in world.npcs:
            if other is npc:
                continue

            if other.location != npc.location:
                continue

            social_system.interact(npc, other, world)
            return True

        return False