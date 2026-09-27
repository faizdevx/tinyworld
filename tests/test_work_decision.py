from WORLD.AI.action import ActionType
from WORLD.NPCs.npc import NPC
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


def test_schedule_is_overridden_by_low_energy():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=20,
        hunger=20,
        food=0,
    )

    world.add_npc(rahul)

    # Schedule says Rahul should work.
    rahul.schedule[8] = "Village Farm"

    world.clock.hour = 8

    simulation = Simulation(world)

    simulation.tick()

    # Schedule moved Rahul to the farm first.
    # Decision system then chose SLEEP.
    # Action executor sent him home and restored energy.
    assert rahul.location == "House 1"
    assert rahul.energy == 35