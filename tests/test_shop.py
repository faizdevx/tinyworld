from WORLD.NPCs.npc import NPC
from WORLD.Buildings.shop import Shop
from WORLD.Economy.trading import buy_food
from WORLD.Economy.money import total_money

def test_npc_can_buy_food():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="General Store",
    )

    shop = Shop(
        name="General Store",
        money=100,
        food=20,
    )

    result = buy_food(rahul, shop)

    assert result is True

    assert rahul.money == 45
    assert rahul.food == 1

    assert shop.money == 105
    assert shop.food == 19

def test_npc_cannot_buy_without_enough_money():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=2,
        home="House 1",
        location="General Store",
    )

    shop = Shop(
        name="General Store",
        money=100,
        food=20,
    )

    result = buy_food(rahul, shop)

    assert result is False

    assert rahul.money == 2
    assert rahul.food == 0

    assert shop.money == 100
    assert shop.food == 20

def test_npc_cannot_buy_when_shop_has_no_food():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="General Store",
    )

    shop = Shop(
        name="General Store",
        money=100,
        food=0,
    )

    result = buy_food(rahul, shop)

    assert result is False

    assert rahul.money == 50
    assert rahul.food == 0

    assert shop.money == 100
    assert shop.food == 0


def test_buy_food_does_not_create_money():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="General Store",
    )

    shop = Shop(
        name="General Store",
        money=100,
        food=20,
    )

    before = total_money([rahul, shop])

    buy_food(rahul, shop)

    after = total_money([rahul, shop])

    assert before == after

def test_shop_uses_its_food_price():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="General Store",
    )

    shop = Shop(
        name="General Store",
        money=100,
        food=20,
        food_price=10,
    )

    result = buy_food(rahul, shop)

    assert result is True
    assert rahul.money == 40
    assert shop.money == 110