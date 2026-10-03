from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.NPCs.npc import NPC


def test_generator_creates_world_from_scenario():
    scenario = WorldScenario(
        resources={
            "Food": 100,
            "Wood": 200,
            "Stone": 50,
        }
    )
    world = WorldGenerator().generate(scenario, seed=42)

    assert world.resources["Food"].quantity == 100
    assert world.resources["Wood"].quantity == 200
    assert world.resources["Stone"].quantity == 50


def test_food_remains_available_through_legacy_world_food():
    scenario = WorldScenario(resources={"Food": 250})
    world = WorldGenerator().generate(scenario)

    assert world.food.quantity == 250
    assert world.resources["Food"] is world.food


def test_resources_are_independent():
    scenario = WorldScenario(resources={"Food": 100, "Wood": 200})
    world = WorldGenerator().generate(scenario)

    world.resources["Wood"].add(50)

    assert world.resources["Wood"].quantity == 250
    assert world.resources["Food"].quantity == 100


def test_same_scenario_and_seed_produce_same_resource_state():
    scenario = WorldScenario(
        resources={
            "Food": 100,
            "Wood": 200,
            "Stone": 50,
        }
    )

    first = WorldGenerator().generate(scenario, seed=42)
    second = WorldGenerator().generate(scenario, seed=42)

    first_state = {
        name: resource.quantity
        for name, resource in first.resources.items()
    }
    second_state = {
        name: resource.quantity
        for name, resource in second.resources.items()
    }

    assert first_state == second_state


def test_generator_creates_buildings_from_scenario():
    scenario = WorldScenario(
        buildings=[
            "Village Farm",
            "General Store",
        ]
    )

    world = WorldGenerator().generate(scenario)

    assert len(world.buildings) == 2


def test_generated_buildings_preserve_scenario_names():
    scenario = WorldScenario(
        buildings=[
            "Village Farm",
            "General Store",
        ]
    )

    world = WorldGenerator().generate(scenario)

    assert [building.name for building in world.buildings] == [
        "Village Farm",
        "General Store",
    ]


def test_generator_assigns_known_building_types():
    scenario = WorldScenario(
        buildings=[
            "Village Farm",
            "General Store",
            "House",
        ]
    )

    world = WorldGenerator().generate(scenario)

    assert [building.building_type for building in world.buildings] == [
        "farm",
        "shop",
        "house",
    ]


def test_generator_allows_unknown_building_as_generic():
    scenario = WorldScenario(buildings=["Temple"])

    world = WorldGenerator().generate(scenario)

    assert len(world.buildings) == 1
    assert world.buildings[0].name == "Temple"
    assert world.buildings[0].building_type == "generic"


def test_building_generation_does_not_reconfigure_world_shop():
    scenario = WorldScenario(buildings=["General Store"])

    world = WorldGenerator().generate(scenario)

    assert world.shop.name == "General Store"
    assert world.shop.money == 100
    assert world.shop.food == 20


def test_generator_creates_requested_population():
    world = WorldGenerator().generate(WorldScenario(population=40))

    assert len(world.npcs) == 40


def test_generator_creates_zero_npcs_for_zero_population():
    world = WorldGenerator().generate(WorldScenario(population=0))

    assert world.npcs == []


def test_generated_population_uses_existing_npc_architecture():
    world = WorldGenerator().generate(WorldScenario(population=1))

    npc = world.npcs[0]

    assert isinstance(npc, NPC)
    assert npc.name == "NPC 1"
    assert npc.role == "villager"
    assert npc.home == "Settlement"
    assert npc.location == "Settlement"
    assert npc.brain is not None


def test_same_scenario_and_seed_produce_same_population_state():
    scenario = WorldScenario(population=3)

    first = WorldGenerator().generate(scenario, seed=42)
    second = WorldGenerator().generate(scenario, seed=42)

    first_state = [
        (npc.name, npc.role, npc.money, npc.home, npc.location)
        for npc in first.npcs
    ]
    second_state = [
        (npc.name, npc.role, npc.money, npc.home, npc.location)
        for npc in second.npcs
    ]

    assert first_state == second_state


def test_generator_creates_landmark_entities():
    scenario = WorldScenario(landmarks=["Forest", "River"])

    world = WorldGenerator().generate(scenario)

    assert [entity.name for entity in world.entities] == [
        "Forest",
        "River",
    ]


def test_generator_assigns_landmark_types():
    scenario = WorldScenario(landmarks=["Forest", "River"])

    world = WorldGenerator().generate(scenario)

    assert [entity.entity_type for entity in world.entities] == [
        "forest",
        "river",
    ]


def test_generator_allows_unknown_landmark_as_generic():
    scenario = WorldScenario(landmarks=["Ancient Ruins"])

    world = WorldGenerator().generate(scenario)

    assert world.entities[0].name == "Ancient Ruins"
    assert world.entities[0].entity_type == "generic"


def test_generator_creates_factions_from_scenario():
    scenario = WorldScenario(
        factions=[
            "Regional Ruler",
            "Merchant Guild",
        ]
    )

    world = WorldGenerator().generate(scenario)

    assert [faction.name for faction in world.factions] == [
        "Regional Ruler",
        "Merchant Guild",
    ]


def test_generator_assigns_known_faction_types():
    scenario = WorldScenario(
        factions=[
            "Regional Ruler",
            "Merchant Guild",
        ]
    )

    world = WorldGenerator().generate(scenario)

    assert [faction.faction_type for faction in world.factions] == [
        "ruler",
        "guild",
    ]


def test_generator_allows_unknown_faction_as_generic():
    scenario = WorldScenario(factions=["Northern Kingdom"])

    world = WorldGenerator().generate(scenario)

    assert world.factions[0].name == "Northern Kingdom"
    assert world.factions[0].faction_type == "generic"


def test_generator_preserves_seeded_world_creation():
    scenario = WorldScenario(resources={"Food": 150})
    first = WorldGenerator().generate(scenario, seed=42)
    second = WorldGenerator().generate(scenario, seed=42)

    assert first.food.quantity == second.food.quantity == 150
    assert first.rng.seed == second.rng.seed == 42
