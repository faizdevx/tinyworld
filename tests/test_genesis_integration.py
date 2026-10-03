from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


def test_generator_builds_complete_scenario():
    scenario = WorldScenario(
        era="15th century",
        geography="small coastal settlement",
        climate="dry",
        population=4,
        resources={
            "Food": 500,
            "Wood": 300,
            "Stone": 100,
        },
        buildings=[
            "Village Farm",
            "General Store",
            "House",
            "House",
        ],
        landmarks=[
            "Forest",
            "River",
            "Coast",
        ],
        factions=[
            "Regional Ruler",
            "Merchant Guild",
        ],
    )

    world = WorldGenerator().generate(scenario, seed=42)

    assert world.metadata == {
        "era": "15th century",
        "geography": "small coastal settlement",
        "climate": "dry",
    }
    assert len(world.npcs) == 4
    assert world.resources["Food"].quantity == 500
    assert world.resources["Wood"].quantity == 300
    assert world.resources["Stone"].quantity == 100
    assert [building.name for building in world.buildings] == [
        "Village Farm",
        "General Store",
        "House",
        "House",
    ]
    assert [entity.name for entity in world.entities] == [
        "Forest",
        "River",
        "Coast",
    ]
    assert [faction.name for faction in world.factions] == [
        "Regional Ruler",
        "Merchant Guild",
    ]


def test_genesis_population_uses_normal_npc_initialization():
    world = WorldGenerator().generate(WorldScenario(population=3))

    assert len(world.npcs) == 3
    assert all(npc.brain is not None for npc in world.npcs)


def test_complete_generation_is_deterministic():
    scenario = WorldScenario(
        population=5,
        resources={
            "Food": 100,
            "Wood": 50,
        },
        buildings=["House"],
        landmarks=["Forest"],
        factions=["Regional Ruler"],
    )

    first = WorldGenerator().generate(scenario, seed=42)
    second = WorldGenerator().generate(scenario, seed=42)

    assert [
        (npc.name, npc.role, npc.money, npc.home, npc.location)
        for npc in first.npcs
    ] == [
        (npc.name, npc.role, npc.money, npc.home, npc.location)
        for npc in second.npcs
    ]
    assert {
        name: resource.quantity
        for name, resource in first.resources.items()
    } == {
        name: resource.quantity
        for name, resource in second.resources.items()
    }
    assert [
        (building.name, building.building_type)
        for building in first.buildings
    ] == [
        (building.name, building.building_type)
        for building in second.buildings
    ]
    assert [
        (entity.name, entity.entity_type)
        for entity in first.entities
    ] == [
        (entity.name, entity.entity_type)
        for entity in second.entities
    ]
    assert [
        (faction.name, faction.faction_type)
        for faction in first.factions
    ] == [
        (faction.name, faction.faction_type)
        for faction in second.factions
    ]


def test_plain_world_does_not_get_scenario_state():
    world = World()

    assert world.metadata == {}
    assert world.resources["Food"] is world.food
    assert world.buildings == []
    assert world.entities == []
    assert world.factions == []
    assert world.npcs == []


def test_generated_world_is_accepted_by_simulation():
    scenario = WorldScenario(
        population=2,
        resources={"Food": 100},
        buildings=["Village Farm"],
    )
    world = WorldGenerator().generate(scenario, seed=42)
    starting_hour = world.clock.hour

    Simulation(world).tick()

    assert world.clock.hour == (starting_hour + 1) % 24