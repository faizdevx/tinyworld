from WORLD.NPCs.npc import NPC
from WORLD.Buildings.shop import Shop
from WORLD.Resources.food import Resource
from WORLD.Shopping.shopping import ShoppingSystem
from WORLD.Needs.needs import NeedsSystem


class FakeClock:
    def __init__(self, hour: int):
        self.hour = hour


class FakeWorld:
    def __init__(self, hour: int):
        self.clock = FakeClock(hour)
        self.npcs = []
        self.shop = Shop(
            name="General Store",
            money=100,
            food=20,
            food_price=5,
        )
        self.food = Resource(
            name="Food",
            quantity=100,
        )


def test_npc_buys_food_at_19():
    world = FakeWorld(19)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=0,
    )

    world.npcs.append(rahul)

    shopping = ShoppingSystem()

    shopping.update(world)

    assert rahul.location == "General Store"

    assert rahul.money == 45
    assert rahul.food == 1

    assert world.shop.money == 105
    assert world.shop.food == 19

def test_shopkeeper_does_not_buy_from_shop():
    world = FakeWorld(19)

    ali = NPC(
        name="Ali",
        role="shopkeeper",
        money=50,
        home="House 2",
        location="General Store",
        food=0,
    )

    world.npcs.append(ali)

    shopping = ShoppingSystem()

    shopping.update(world)

    assert ali.money == 50
    assert ali.food == 0
    assert world.shop.money == 100
    assert world.shop.food == 20


def test_npc_with_food_does_not_buy_again():
    world = FakeWorld(19)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
    )

    world.npcs.append(rahul)

    shopping = ShoppingSystem()

    shopping.update(world)

    assert rahul.money == 50
    assert rahul.food == 1
    assert world.shop.money == 100
    assert world.shop.food == 20


def test_shopping_does_not_happen_before_19():
    world = FakeWorld(18)

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=0,
    )

    world.npcs.append(rahul)

    shopping = ShoppingSystem()

    shopping.update(world)

    assert rahul.money == 50
    assert rahul.food == 0
    assert world.shop.money == 100
    assert world.shop.food == 20


def test_npc_buys_food_then_eats():
    world = FakeWorld(19)

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

    shopping = ShoppingSystem()
    needs = NeedsSystem()

    # 19:00
    shopping.update(world)

    assert rahul.money == 45
    assert rahul.food == 1

    # Move simulation hour to 20:00.
    world.clock.hour = 20

    needs.update(world)

    assert rahul.food == 0
    assert rahul.energy == 70