from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource
from WORLD.Farming.farming import FarmingSystem
from WORLD.Events.event_log import EventLog


class FakeClock:
    def __init__(self, hour: int, day: int = 1):
        self.hour = hour
        self.day = day


class FakeWorld:
    def __init__(self, hour: int, day: int = 1):
        self.clock = FakeClock(hour, day)
        self.npcs = []

        self.food = Resource(
            name="Food",
            quantity=100,
        )

        self.event_log = EventLog()


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

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "HARVEST"
    assert event.day == 1
    assert event.hour == 12
    assert event.actor == "Village"


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
    assert world.event_log.events == []


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
    assert world.event_log.events == []


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
    assert world.event_log.events == []


def test_production_depends_on_number_of_farmers():
    world = FakeWorld(12)

    world.npcs.extend(
        [
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
        ]
    )

    farming = FarmingSystem()

    farming.update(world)

    assert world.food.quantity == 104

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "HARVEST"
    assert event.description == "Farmers produced 4 food."


def test_low_energy_farmer_produces_less_food():
    world = FakeWorld(12)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
        energy=20,
    )

    world.npcs.append(rahul)

    FarmingSystem().update(world)

    assert world.food.quantity == 101

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "HARVEST"
    assert event.description == "Farmers produced 1 food."



def test_unworked_farmer_does_not_produce_food():
    world = FakeWorld(12)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
    )

    world.npcs.append(rahul)

    world.work_status = {
        "Rahul": "absent",
    }

    FarmingSystem().update(world)

    assert world.food.quantity == 100

def test_worked_farmer_produces_food():
    world = FakeWorld(12)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
    )

    world.npcs.append(rahul)

    world.work_status = {
        "Rahul": "worked",
    }

    FarmingSystem().update(world)

    assert world.food.quantity == 102