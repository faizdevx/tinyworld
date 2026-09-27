from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource
from WORLD.Farming.farming import FarmingSystem


class FakeClock:
    def __init__(self, hour: int):
        self.hour = hour


class FakeWorld:
    def __init__(self, hour: int):
        self.clock = FakeClock(hour)
        self.npcs = []
        self.food = Resource(
            name="Food",
            quantity=100,
        )


def test_four_farmers_produce_eight_food():
    world = FakeWorld(12)

    for name in ["Rahul", "Arjun", "Vikram", "Ravi"]:
        world.npcs.append(
            NPC(
                name=name,
                role="farmer",
                money=50,
                home="House 1",
                location="Village Farm",
            )
        )

    farming = FarmingSystem()

    farming.update(world)

    assert world.food.quantity == 108


def test_farmer_not_at_farm_produces_nothing():
    world = FakeWorld(12)

    world.npcs.append(
        NPC(
            name="Rahul",
            role="farmer",
            money=50,
            home="House 1",
            location="House 1",
        )
    )

    farming = FarmingSystem()

    farming.update(world)

    assert world.food.quantity == 100

def test_farming_does_not_happen_before_noon():
    world = FakeWorld(11)

    world.npcs.append(
        NPC(
            name="Rahul",
            role="farmer",
            money=50,
            home="House 1",
            location="Village Farm",
        )
    )

    farming = FarmingSystem()

    farming.update(world)

    assert world.food.quantity == 100


def test_non_farmer_at_farm_produces_nothing():
    world = FakeWorld(12)

    world.npcs.append(
        NPC(
            name="Ali",
            role="shopkeeper",
            money=50,
            home="House 2",
            location="Village Farm",
        )
    )

    farming = FarmingSystem()

    farming.update(world)

    assert world.food.quantity == 100


def test_production_depends_on_number_of_farmers():
    world = FakeWorld(12)

    world.npcs.extend([
        NPC(
            name="Rahul",
            role="farmer",
            money=50,
            home="House 1",
            location="Village Farm",
        ),
        NPC(
            name="Arjun",
            role="farmer",
            money=50,
            home="House 1",
            location="Village Farm",
        ),
    ])

    farming = FarmingSystem()

    farming.update(world)

    assert world.food.quantity == 104