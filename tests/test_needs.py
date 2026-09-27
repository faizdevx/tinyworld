from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource
from WORLD.Needs.needs import NeedsSystem


class FakeClock:
    def __init__(self, hour: int):
        self.hour = hour


class FakeWorld:
    def __init__(self, hour: int, food_quantity: int = 100):
        self.clock = FakeClock(hour)
        self.npcs = []
        self.food = Resource(
            name="Food",
            quantity=food_quantity,
        )


def test_population_consumes_food_at_20():
    world = FakeWorld(20)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
        energy=50,
    )

    ali = NPC(
        name="Ali",
        role="shopkeeper",
        money=50,
        home="House 2",
        location="House 2",
        food=1,
        energy=60,
    )

    world.npcs.extend([rahul, ali])

    needs = NeedsSystem()

    needs.update(world)

    assert rahul.food == 0
    assert ali.food == 0

    assert rahul.energy == 70
    assert ali.energy == 80

    assert world.food.quantity == 100


def test_population_does_not_consume_before_20():
    world = FakeWorld(19)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
        energy=50,
    )

    world.npcs.append(rahul)

    needs = NeedsSystem()

    needs.update(world)

    assert world.food.quantity == 100
    assert rahul.food == 1
    assert rahul.energy == 50


def test_npc_without_food_does_not_gain_energy():
    world = FakeWorld(20)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=0,
        energy=50,
    )

    world.npcs.append(rahul)

    needs = NeedsSystem()

    needs.update(world)

    assert rahul.food == 0
    assert rahul.energy == 50


def test_energy_cannot_exceed_100():
    world = FakeWorld(20)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
        energy=90,
    )

    world.npcs.append(rahul)

    needs = NeedsSystem()

    needs.update(world)

    assert world.food.quantity == 100
    assert rahul.food == 0
    assert rahul.energy == 100