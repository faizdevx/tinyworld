from types import SimpleNamespace

from WORLD.AI.brain import Brain
from WORLD.NPCs.npc import NPC
from WORLD.world import World


class FakeBrain:
    def __init__(self):
        self.calls = []

    def update(self, world):
        self.calls.append(world)
        return True


def test_agent_system_delegates_to_npc_brain():
    world = World()

    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(npc)

    fake_brain = FakeBrain()
    npc.brain = fake_brain

    world.agent_system.update(world)

    assert fake_brain.calls == [world]


def test_agent_system_attaches_brain_when_missing():
    world = World()

    npc = SimpleNamespace(
        name="Rahul",
        hunger=20,
        energy=80,
        money=50,
        food=1,
        location="House 1",
        schedule={},
        memories=[],
        current_goal=None,
        active_plan=None,
        brain=None,
        eat=lambda: True,
    )

    world.npcs.append(npc)

    world.agent_system.update(world)

    assert npc.brain is not None
    assert isinstance(npc.brain, Brain)
