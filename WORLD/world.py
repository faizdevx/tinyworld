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
from WORLD.Work.work import WorkSystem
from WORLD.Rest.rest import RestSystem
from WORLD.Social.social import SocialSystem
from WORLD.AI.decision import DecisionSystem
from WORLD.AI.action_executor import ActionExecutor
from WORLD.system.agent import AgentSystem
from WORLD.Events.event_log import EventLog
from WORLD.Economy.pricing import PricingSystem
from WORLD.Cooperation.cooperation import CooperationSystem
from WORLD.Conflict.conflict import ConflictSystem
from WORLD.Social.reputation import ReputationSystem
from WORLD.Simulation.rng import SimulationRNG
from WORLD.Environment.environment import EnvironmentSystem


class World:

    def __init__(self,seed:int=42):
        # -------------------------
        # Time
        # -------------------------
        self.clock = Clock()

        # -------------------------
        # Entities
        # -------------------------
        self.npcs: list[NPC] = []
        self.buildings: list[Building] = []

        # -------------------------
        # Resources
        # -------------------------
        self.food = Resource(
            name="Food",
            quantity=100,
        )

        # -------------------------
        # Shop
        # -------------------------
        self.shop = Shop(
            name="General Store",
            money=100,
            food=20,
            food_price=5,
        )

        # -------------------------
        # Systems
        # -------------------------
        self.schedule_system = ScheduleSystem()
        self.farming_system = FarmingSystem()
        self.restocking_system = RestockingSystem()
        self.shopping_system = ShoppingSystem()
        self.needs_system = NeedsSystem()
        self.work_status: dict[str, str] = {}
        self.rest_system=RestSystem()
        self.social_system = SocialSystem()
        self.decision_system = DecisionSystem()
        self.action_executor = ActionExecutor()
        self.pricing_system = PricingSystem()
        self.agent_system = AgentSystem(
            self.decision_system
            )
        self.event_log = EventLog()
        self.conflict_system = ConflictSystem()
        self.cooperation_system = CooperationSystem()
        self.reputation_system = ReputationSystem()
        self.rng = SimulationRNG(seed)

        self.environment_system = EnvironmentSystem(
            random_events_enabled=False
        )


    def add_npc(self, npc: NPC) -> None:
        self.npcs.append(npc)

    def add_building(self, building: Building) -> None:
        self.buildings.append(building)