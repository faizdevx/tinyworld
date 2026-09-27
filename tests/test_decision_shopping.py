from WORLD.NPCs.npc import NPC
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


def test_simulation_uses_decision_to_trigger_shopping():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(rahul)

    # Deliberately choose an arbitrary hour.
    # Shopping should happen because of state, not the clock.
    world.clock.hour = 10

    rahul.hunger = 85
    rahul.energy = 100
    rahul.food = 0

    simulation = Simulation(world)

    simulation.tick()

    assert rahul.food == 1
    assert rahul.money == 45

    assert world.shop.food == 19
    assert world.shop.money == 105