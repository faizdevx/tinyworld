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
from WORLD.AI.brain import Brain
from WORLD.AI.plan_executor import PlanExecutor
from WORLD.AI.observation import ObservationSystem
from WORLD.AI.perception import Perception
from WORLD.system.agent import AgentSystem
from WORLD.Events.event_log import EventLog
from WORLD.Events.engine import EventEngine
from WORLD.Communication import CommunicationEngine
from WORLD.Economy.pricing import PricingSystem
from WORLD.Cooperation.cooperation import CooperationSystem
from WORLD.Conflict.conflict import ConflictSystem
from WORLD.Social.reputation import ReputationSystem
from WORLD.Simulation.rng import SimulationRNG
from WORLD.Environment.environment import EnvironmentSystem
from WORLD.Entities.entity import WorldEntity
from WORLD.Factions.faction import Faction
from WORLD.Interventions.engine import InterventionEngine
from WORLD.Interventions.models import InterventionAudit


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
        self.entities: list[WorldEntity] = []
        self.factions: list[Faction] = []
        self.metadata: dict[str, str] = {}
        self.rules: dict[str, object] = {}
        self.intervention_history: list[InterventionAudit] = []
        self.intervention_engine = InterventionEngine()
        self.observation_system = ObservationSystem()

        # -------------------------
        # Resources
        # -------------------------
        self.food = Resource(
            name="Food",
            quantity=100,
        )
        self.resources: dict[str, Resource] = {
            "Food": self.food,
        }

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
            self.decision_system,
            perception=Perception(self.observation_system),
            )
        self.event_log = EventLog()
        self.event_engine = EventEngine()
        self.communication_engine = CommunicationEngine()
        self.conflict_system = ConflictSystem()
        self.cooperation_system = CooperationSystem()
        self.reputation_system = ReputationSystem()
        self.rng = SimulationRNG(seed)

        self.environment_system = EnvironmentSystem(
            random_events_enabled=False
        )


    def add_npc(self, npc: NPC) -> None:
        npc.brain = Brain(
            npc=npc,
            perception=self.agent_system.perception,
            goal_system=self.agent_system.goal_system,
            planner=self.agent_system.planner,
            replanner=self.agent_system.replanner,
            memory_retriever=self.agent_system.memory_retriever,
            decision_system=self.decision_system,
            action_executor=self.action_executor,
            plan_executor=PlanExecutor(
                self.action_executor,
            ),
            reasoner=self.agent_system.reasoner,
            reflection=self.agent_system.reflection,
            experience_reflector=(
                self.agent_system.experience_reflector
            ),
            knowledge_extractor=(
                self.agent_system.knowledge_extractor
            ),
            reflection_scheduler=(
                self.agent_system.reflection_scheduler
            ),
            experience_influence=(
                self.agent_system.experience_influence
            ),
        )

        self.npcs.append(npc)

    def add_building(self, building: Building) -> None:
        self.buildings.append(building)

    def add_entity(self, entity: WorldEntity) -> None:
        self.entities.append(entity)

    def add_faction(self, faction: Faction) -> None:
        self.factions.append(faction)
