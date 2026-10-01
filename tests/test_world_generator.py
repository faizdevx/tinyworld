from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario


def test_generator_creates_world_from_scenario():
    scenario = WorldScenario(resources={"Food": 250})
    world = WorldGenerator().generate(scenario, seed=42)

    assert world.food.quantity == 250


def test_generator_preserves_seeded_world_creation():
    scenario = WorldScenario(resources={"Food": 150})
    first = WorldGenerator().generate(scenario, seed=42)
    second = WorldGenerator().generate(scenario, seed=42)

    assert first.food.quantity == second.food.quantity == 150
    assert first.rng.seed == second.rng.seed == 42
