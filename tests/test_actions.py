from WORLD.AI.action import BuyFoodAction
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def create_npc():
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="General Store",
    )


def test_buy_food_requires_correct_location():
    world = World()

    rahul = create_npc()
    rahul.location = "House 1"

    world.add_npc(rahul)
    world.shop.food = 5
    world.shop.food_price = 5

    action = BuyFoodAction()

    assert action.can_execute(rahul, world) is False


def test_buy_food_requires_enough_money():
    world = World()

    rahul = create_npc()
    rahul.money = 4

    world.add_npc(rahul)
    world.shop.food = 5
    world.shop.food_price = 5

    action = BuyFoodAction()

    assert action.can_execute(rahul, world) is False


def test_buy_food_requires_shop_stock():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)
    world.shop.food = 0
    world.shop.food_price = 5

    action = BuyFoodAction()

    assert action.can_execute(rahul, world) is False


def test_buy_food_changes_world_state():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)
    world.shop.food = 5
    world.shop.food_price = 5
    world.shop.money = 100

    action = BuyFoodAction()

    assert action.execute(rahul, world) is True

    assert rahul.money == 45
    assert rahul.food == 1
    assert world.shop.food == 4
    assert world.shop.money == 105
    assert len(world.event_log.events) == 1
    assert world.event_log.events[0].event_type == "PURCHASE"