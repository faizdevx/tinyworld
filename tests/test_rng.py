from WORLD.Simulation.rng import SimulationRNG


def test_same_seed_produces_same_random_sequence():
    rng_a = SimulationRNG(seed=42)
    rng_b = SimulationRNG(seed=42)

    values_a = [
        rng_a.random_float(),
        rng_a.random_float(),
        rng_a.randint(1, 100),
        rng_a.choice(["a", "b", "c"]),
    ]

    values_b = [
        rng_b.random_float(),
        rng_b.random_float(),
        rng_b.randint(1, 100),
        rng_b.choice(["a", "b", "c"]),
    ]

    assert values_a == values_b


def test_different_seeds_produce_different_sequence():
    rng_a = SimulationRNG(seed=42)
    rng_b = SimulationRNG(seed=99)

    values_a = [
        rng_a.random_float(),
        rng_a.randint(1, 100),
    ]

    values_b = [
        rng_b.random_float(),
        rng_b.randint(1, 100),
    ]

    assert values_a != values_b


def test_rng_is_independent_between_instances():
    rng_a = SimulationRNG(seed=42)
    rng_b = SimulationRNG(seed=42)

    first_a = rng_a.random_float()

    # Advancing one RNG must not advance the other.
    first_b = rng_b.random_float()

    assert first_a == first_b


def test_world_has_seeded_rng():
    from WORLD.world import World

    world = World(seed=42)

    assert hasattr(world, "rng")
    assert world.rng.seed == 42