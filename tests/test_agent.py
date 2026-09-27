from WORLD.AI.action import ActionType
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def test_agent_system_makes_one_decision_and_executes_it():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        hunger=85,
        energy=50,
        food=1,
    )

    world.add_npc(rahul)

    world.agent_system.update(world)

    # Rahul has food and high hunger,
    # so the decision should be EAT.
    assert rahul.food == 0
    assert rahul.hunger == 45
    assert rahul.energy == 70