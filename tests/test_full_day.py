from WORLD.Simulation.simulation import Simulation
from WORLD.Village.village import Village


def test_full_day_is_deterministic():
    """
    Run one complete 24-hour simulation and verify that the major
    systems work together without violating core invariants.
    """

    village = Village()
    world = village.create()
    simulation = Simulation(world)

    # Village starts at 08:00.
    assert world.clock.hour == 8

    initial_total_money = (
        sum(npc.money for npc in world.npcs)
        + world.shop.money
        + sum(building.money for building in world.buildings)
    )

    simulation.run(24)

    assert world.clock.hour == 8

    assert world.food.quantity == 99
    assert world.shop.food == 12
    assert world.shop.money == 165

    rahul = next(npc for npc in world.npcs if npc.name == "Rahul")
    arjun = next(npc for npc in world.npcs if npc.name == "Arjun")
    ali = next(npc for npc in world.npcs if npc.name == "Ali")
    sara = next(npc for npc in world.npcs if npc.name == "Sara")



    final_total_money = (
        sum(npc.money for npc in world.npcs)
        + world.shop.money
        + sum(building.money for building in world.buildings)
    )

    assert final_total_money == initial_total_money

    assert world.food.quantity >= 0
    assert world.shop.food >= 0

    for npc in world.npcs:
        assert npc.money >= 0
        assert npc.food >= 0
        assert 0 <= npc.energy <= 100
        assert 0 <= npc.hunger <= 100