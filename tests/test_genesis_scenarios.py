from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


def scenario_a() -> WorldScenario:
    return WorldScenario(
        era="15th century",
        geography="small coastal settlement",
        climate="dry",
        population=40,
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
        factions=[
            "Regional Ruler",
            "Merchant Guild",
        ],
        landmarks=[
            "Forest",
            "River",
            "Coast",
        ],
    )


def scenario_b() -> WorldScenario:
    return WorldScenario(
        era="15th century",
        geography="mountain village",
        climate="cold",
        population=20,
        resources={
            "Food": 300,
            "Wood": 500,
            "Stone": 250,
        },
        buildings=[
            "House",
            "House",
            "Workshop",
        ],
        factions=["Regional Ruler"],
        landmarks=[
            "Forest",
            "Hill",
        ],
    )


def scenario_c() -> WorldScenario:
    return WorldScenario(
        era="16th century",
        geography="river trading settlement",
        climate="temperate",
        population=60,
        resources={
            "Food": 800,
            "Wood": 400,
            "Stone": 150,
        },
        buildings=[
            "General Store",
            "Workshop",
            "House",
            "House",
        ],
        factions=[
            "Merchant Guild",
            "Village Council",
        ],
        landmarks=[
            "River",
            "Coast",
        ],
    )


def world_signature(world: World) -> dict:
    return {
        "metadata": dict(world.metadata),
        "resources": {
            name: resource.quantity
            for name, resource in world.resources.items()
        },
        "buildings": [
            (building.name, building.building_type)
            for building in world.buildings
        ],
        "entities": [
            (entity.name, entity.entity_type)
            for entity in world.entities
        ],
        "factions": [
            (faction.name, faction.faction_type)
            for faction in world.factions
        ],
        "npcs": [
            (
                npc.name,
                npc.role,
                npc.money,
                npc.home,
                npc.location,
            )
            for npc in world.npcs
        ],
    }


def test_scenario_a_generates_complete_coastal_world():
    world = WorldGenerator().generate(scenario_a(), seed=42)

    assert world.metadata == {
        "era": "15th century",
        "geography": "small coastal settlement",
        "climate": "dry",
    }
    assert world.resources["Food"].quantity == 500
    assert world.resources["Wood"].quantity == 300
    assert world.resources["Stone"].quantity == 100
    assert len(world.buildings) == 4
    assert len(world.entities) == 3
    assert len(world.factions) == 2
    assert len(world.npcs) == 40
    assert all(npc.brain is not None for npc in world.npcs)


def test_scenario_b_generates_different_mountain_world():
    world = WorldGenerator().generate(scenario_b(), seed=42)

    assert world.metadata["geography"] == "mountain village"
    assert world.metadata["climate"] == "cold"
    assert world.resources["Food"].quantity == 300
    assert world.resources["Wood"].quantity == 500
    assert world.resources["Stone"].quantity == 250
    assert len(world.npcs) == 20
    assert len(world.factions) == 1
    assert len(world.entities) == 2


def test_scenario_c_generates_different_trading_world():
    world = WorldGenerator().generate(scenario_c(), seed=42)

    assert world.metadata["era"] == "16th century"
    assert world.metadata["geography"] == "river trading settlement"
    assert len(world.npcs) == 60
    assert len(world.factions) == 2
    assert len(world.entities) == 2


def test_one_generator_creates_three_different_worlds():
    generator = WorldGenerator()

    world_a = generator.generate(scenario_a(), seed=42)
    world_b = generator.generate(scenario_b(), seed=42)
    world_c = generator.generate(scenario_c(), seed=42)

    assert len(world_a.npcs) == 40
    assert len(world_b.npcs) == 20
    assert len(world_c.npcs) == 60
    assert world_a.metadata["geography"] != world_b.metadata["geography"]
    assert world_b.metadata["geography"] != world_c.metadata["geography"]


def test_same_scenario_and_seed_are_deterministic():
    generator = WorldGenerator()

    first = generator.generate(scenario_a(), seed=42)
    second = generator.generate(scenario_a(), seed=42)

    assert world_signature(first) == world_signature(second)


def test_different_scenarios_produce_different_worlds():
    generator = WorldGenerator()

    world_a = generator.generate(scenario_a(), seed=42)
    world_b = generator.generate(scenario_b(), seed=42)

    assert world_signature(world_a) != world_signature(world_b)


def test_multiple_generated_scenarios_are_simulation_ready():
    generator = WorldGenerator()

    for scenario in (scenario_a(), scenario_b(), scenario_c()):
        world = generator.generate(scenario, seed=42)
        Simulation(world).tick()


def test_plain_world_remains_unconfigured():
    world = World()

    assert world.metadata == {}
    assert world.resources["Food"] is world.food
    assert world.buildings == []
    assert world.entities == []
    assert world.factions == []
    assert world.npcs == []
