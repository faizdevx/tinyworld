from WORLD.AI.agent import AgentSystem as LegacyAgentSystem
from WORLD.NPCs.npc import NPC
from WORLD.system.agent import AgentSystem
from WORLD.world import World


def test_legacy_agent_system_import_points_to_canonical_class():
    assert LegacyAgentSystem is AgentSystem


def test_agent_system_has_single_canonical_implementation():
    from WORLD.AI.agent import AgentSystem as legacy
    from WORLD.system.agent import AgentSystem as canonical

    assert legacy.__module__ == "WORLD.system.agent"
    assert canonical.__module__ == "WORLD.system.agent"


def test_legacy_agent_system_can_still_update_world():
    world = World()

    npc = NPC(
        name="Rahul",
        role="worker",
        money=50,
        home="Home",
        location="Home",
    )

    world.add_npc(npc)

    legacy = LegacyAgentSystem(world.decision_system)
    legacy.update(world)

    assert npc.brain is not None
