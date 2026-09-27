from WORLD.NPCs.npc import NPC
from WORLD.Work.work import WorkSystem


class FakeWorld:
    def __init__(self):
        self.npcs = []


def test_work_reduces_energy():
    world = FakeWorld()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
        energy=80,
    )

    world.npcs.append(rahul)

    WorkSystem().update(world)

    assert rahul.energy == 75


def test_not_working_at_home():
    world = FakeWorld()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=80,
    )

    world.npcs.append(rahul)

    WorkSystem().update(world)

    assert rahul.energy == 80


def test_work_cannot_make_energy_negative():
    world = FakeWorld()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
        energy=2,
    )

    world.npcs.append(rahul)

    WorkSystem().update(world)

    assert rahul.energy == 0