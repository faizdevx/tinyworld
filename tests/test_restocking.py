from WORLD.Resources.food import Resource
from WORLD.Buildings.shop import Shop
from WORLD.Restocking.restocking import RestockingSystem
from WORLD.Events.event_log import EventLog


class FakeClock:
    def __init__(self, hour: int, day: int = 1):
        self.hour = hour
        self.day = day


class FakeWorld:
    def __init__(
        self,
        hour: int,
        village_food: int = 100,
        shop_food: int = 20,
        day: int = 1,
    ):
        self.clock = FakeClock(hour, day)

        self.food = Resource(
            name="Food",
            quantity=village_food,
        )

        self.shop = Shop(
            name="General Store",
            money=100,
            food=shop_food,
            food_price=5,
        )

        self.event_log = EventLog()


def test_shop_restocked_at_13():
    world = FakeWorld(13)

    system = RestockingSystem()

    system.update(world)

    assert world.food.quantity == 95
    assert world.shop.food == 25

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "RESTOCK"
    assert event.day == 1
    assert event.hour == 13
    assert event.actor == "Village"
    assert event.target == "General Store"


def test_restocking_does_not_happen_before_13():
    world = FakeWorld(12)

    system = RestockingSystem()

    system.update(world)

    assert world.food.quantity == 100
    assert world.shop.food == 20
    assert world.event_log.events == []


def test_restocking_does_not_happen_after_13():
    world = FakeWorld(14)

    system = RestockingSystem()

    system.update(world)

    assert world.food.quantity == 100
    assert world.shop.food == 20
    assert world.event_log.events == []


def test_restocking_fails_when_village_has_insufficient_food():
    world = FakeWorld(
        hour=13,
        village_food=3,
        shop_food=20,
    )

    system = RestockingSystem()

    system.update(world)

    assert world.food.quantity == 3
    assert world.shop.food == 20
    assert world.event_log.events == []


def test_restocking_preserves_total_food():
    world = FakeWorld(
        hour=13,
        village_food=100,
        shop_food=20,
    )

    before = (
        world.food.quantity
        + world.shop.food
    )

    RestockingSystem().update(world)

    after = (
        world.food.quantity
        + world.shop.food
    )

    assert before == after

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "RESTOCK"