from WORLD.Village.village import Village
from WORLD.Simulation.simulation import Simulation


def test_simulation_tick_advances_clock():
    world = Village().create()

    simulation = Simulation(world)

    starting_hour = world.clock.hour

    simulation.tick()

    assert world.clock.hour == (starting_hour + 1) % 24


def test_simulation_updates_npc_schedule():
    world = Village().create()

    world.clock.hour = 8

    simulation = Simulation(world)

    simulation.tick()

    rahul = next(
        npc
        for npc in world.npcs
        if npc.name == "Rahul"
    )

    assert rahul.location == "Village Farm"


def test_simulation_runs_farming():
    world = Village().create()

    world.clock.hour = 12

    simulation = Simulation(world)

    simulation.tick()

    # Rahul + Arjun = 2 farmers
    # 2 × 2 food = 4 food
    assert world.food.quantity == 104


def test_simulation_runs_needs():
    world = Village().create()

    world.clock.hour = 20

    for npc in world.npcs:
        npc.food = 1
        npc.energy = 50
        npc.hunger = 80

    simulation = Simulation(world)

    simulation.tick()

    for npc in world.npcs:
        # Hunger increases first:
        # 80 -> 84
        # Then EAT:
        # 84 -> 44
        assert npc.food == 0
        assert npc.hunger == 44
        assert npc.energy == 70

        
def test_full_tick_pipeline():
    world = Village().create()

    world.clock.hour = 12

    simulation = Simulation(world)

    rahul = next(
        npc
        for npc in world.npcs
        if npc.name == "Rahul"
    )

    simulation.tick()

    assert rahul.location == "Village Farm"

    # Two farmers produce:
    # 2 × 2 = 4
    assert world.food.quantity == 104

    # Clock moved from 12 -> 13.
    assert world.clock.hour == 13



def test_simulation_restocking_moves_food_to_shop():
    world = Village().create()

    world.clock.hour = 13

    simulation = Simulation(world)

    simulation.tick()

    assert world.food.quantity == 95
    assert world.shop.food == 25


def test_simulation_food_moves_from_farm_to_shop():
    world = Village().create()

    simulation = Simulation(world)

    # Process 12:00.
    world.clock.hour = 12

    simulation.tick()

    assert world.food.quantity == 104

    # Process 13:00.
    simulation.tick()

    assert world.food.quantity == 99
    assert world.shop.food == 25