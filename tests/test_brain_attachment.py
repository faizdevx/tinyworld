from WORLD.AI.brain import Brain
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def test_world_attaches_brain_to_npc():
    world = World()

    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(npc)

    assert npc.brain is not None
    assert isinstance(npc.brain, Brain)


def test_npc_brain_receives_world_cognition_components():
    world = World()

    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(npc)

    assert npc.brain.perception is world.agent_system.perception
    assert npc.brain.goal_system is world.agent_system.goal_system
    assert npc.brain.planner is world.agent_system.planner
    assert npc.brain.replanner is world.agent_system.replanner
    assert (
        npc.brain.memory_retriever
        is world.agent_system.memory_retriever
    )
    assert npc.brain.decision_system is world.decision_system
    assert npc.brain.action_executor is world.action_executor
    assert npc.brain.plan_executor is not None
    assert (
        npc.brain.experience_reflector
        is world.agent_system.experience_reflector
    )
