from WORLD.Clock.clock import Clock
from WORLD.Buildings.buildings import Building
from WORLD.Buildings.shop import Shop
from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource
from WORLD.Schedules.schedule import ScheduleSystem
from WORLD.Farming.farming import FarmingSystem
from WORLD.Needs.needs import NeedsSystem
from WORLD.Shopping.shopping import ShoppingSystem
from WORLD.Restocking.restocking import RestockingSystem


class World:

    def __init__(self):
        self.clock = Clock()
        self.shopping_system=ShoppingSystem()
        self.npcs: list[NPC] = []
        self.buildings: list[Building] = []
        self.restocking_system = RestockingSystem()
        self.food = Resource(
            name="Food",
            quantity=100,
        )

        self.shop = Shop(
            name="General Store",
            money=100,
            food=20,
            food_price=5,
        )

        self.schedule_system = ScheduleSystem()
        self.farming_system = FarmingSystem()
        self.needs_system = NeedsSystem()

    def add_npc(self, npc: NPC) -> None:
        self.npcs.append(npc)

    def add_building(self, building: Building) -> None:
        self.buildings.append(building)