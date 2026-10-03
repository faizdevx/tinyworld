from WORLD.world import World
from WORLD.Buildings.buildings import Building
from WORLD.Entities.entity import WorldEntity
from WORLD.Factions.faction import Faction
from WORLD.Genesis.scenario import WorldScenario
from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource


BUILDING_TYPES = {
    "Village Farm": "farm",
    "General Store": "shop",
    "House": "house",
    "Workshop": "workshop",
}

ENTITY_TYPES = {
    "Forest": "forest",
    "River": "river",
    "Hill": "hill",
    "Coast": "coast",
}

FACTION_TYPES = {
    "Regional Ruler": "ruler",
    "Merchant Guild": "guild",
    "Village Council": "council",
}


class WorldGenerator:
    """
    Converts a declarative scenario into a concrete World.

    The Genesis layer creates initial state; the Simulation layer
    mutates the world after creation.
    """

    def generate(
        self,
        scenario: WorldScenario,
        *,
        seed: int = 42,
    ) -> World:
        world = World(seed=seed)
        self._apply_metadata(world, scenario)
        self._apply_resources(world, scenario)
        self._apply_buildings(world, scenario)
        self._apply_population(world, scenario)
        self._apply_landmarks(world, scenario)
        self._apply_factions(world, scenario)
        return world

    def _apply_metadata(self, world: World, scenario: WorldScenario) -> None:
        world.metadata = {
            "era": scenario.era,
            "geography": scenario.geography,
            "climate": scenario.climate,
        }

    def _apply_resources(self, world: World, scenario: WorldScenario) -> None:
        for name, quantity in scenario.resources.items():
            resource = world.resources.get(name)
            if resource is None:
                resource = Resource(name=name, quantity=quantity)
                world.resources[name] = resource
            else:
                resource.quantity = quantity

    def _apply_buildings(self, world: World, scenario: WorldScenario) -> None:
        for name in scenario.buildings:
            building = Building(
                name=name,
                building_type=BUILDING_TYPES.get(name, "generic"),
            )
            world.add_building(building)

    def _apply_population(self, world: World, scenario: WorldScenario) -> None:
        for index in range(scenario.population):
            npc = NPC(
                name=f"NPC {index + 1}",
                role="villager",
                money=0,
                home="Settlement",
                location="Settlement",
            )
            world.add_npc(npc)

    def _apply_landmarks(self, world: World, scenario: WorldScenario) -> None:
        for name in scenario.landmarks:
            entity = WorldEntity(
                name=name,
                entity_type=ENTITY_TYPES.get(name, "generic"),
            )
            world.add_entity(entity)

    def _apply_factions(self, world: World, scenario: WorldScenario) -> None:
        for name in scenario.factions:
            faction = Faction(
                name=name,
                faction_type=FACTION_TYPES.get(name, "generic"),
            )
            world.add_faction(faction)
