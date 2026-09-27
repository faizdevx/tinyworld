from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource
from WORLD.Needs.needs import NeedsSystem


class FakeClock:
    def __init__(self, hour: int):
        self.hour = hour


class FakeWorld:
    def __init__(
        self,
        hour: int,
        food_quantity: int = 100,
    ):
        self.clock = FakeClock(hour)
        self.npcs = []
        self.food = Resource(
            name="Food",
            quantity=food_quantity,
        )


def test_hunger_increases_over_time():
    world = FakeWorld(10)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        hunger=20,
    )

    world.npcs.append(rahul)

    NeedsSystem().update(world)

    assert rahul.hunger == 24


def test_npc_eats_at_20():
    world = FakeWorld(20)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
        hunger=60,
        energy=50,
    )

    world.npcs.append(rahul)

    NeedsSystem().update(world)

    assert rahul.food == 0
    assert rahul.hunger == 24
    assert rahul.energy == 70


def test_npc_without_food_becomes_less_energetic():
    world = FakeWorld(20)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=0,
        hunger=69,
        energy=50,
    )

    world.npcs.append(rahul)

    NeedsSystem().update(world)

    # Hunger: 69 + 4 = 73
    # Then severe hunger penalty: -5 energy.
    assert rahul.hunger == 73
    assert rahul.energy == 45


def test_food_is_not_taken_from_global_food_pool():
    world = FakeWorld(20)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
        hunger=50,
        energy=50,
    )

    world.npcs.append(rahul)

    NeedsSystem().update(world)

    assert world.food.quantity == 100