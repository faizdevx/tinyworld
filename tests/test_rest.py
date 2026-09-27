from WORLD.NPCs.npc import NPC
from WORLD.Rest.rest import RestSystem


class FakeClock:
    def __init__(self, hour: int):
        self.hour = hour


class FakeWorld:
    def __init__(self, hour: int):
        self.clock = FakeClock(hour)
        self.npcs = []


def test_npc_recovers_energy_while_sleeping():
    world = FakeWorld(22)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=50,
    )

    world.npcs.append(rahul)

    RestSystem().update(world)

    assert rahul.energy == 65


def test_npc_recovers_energy_after_midnight():
    world = FakeWorld(2)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=50,
    )

    world.npcs.append(rahul)

    RestSystem().update(world)

    assert rahul.energy == 65



def test_npc_does_not_sleep_during_day():
    world = FakeWorld(14)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=50,
    )

    world.npcs.append(rahul)

    RestSystem().update(world)

    assert rahul.energy == 50

def test_npc_does_not_sleep_away_from_home():
    world = FakeWorld(22)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
        energy=50,
    )

    world.npcs.append(rahul)

    RestSystem().update(world)

    assert rahul.energy == 50