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
        hunger=85,
        energy=100,
        food=0,
    )

    world.add_npc(rahul)

    world.clock.hour = 10

    simulation = Simulation(world)
    simulation.tick()

    # Shopping happened first.
    assert rahul.money == 45

    # NeedsSystem then saw that Rahul had food and decided to eat.
    assert rahul.food == 1
    assert rahul.hunger == 89
    assert rahul.energy == 95

    assert world.shop.food == 19
    assert world.shop.money == 105