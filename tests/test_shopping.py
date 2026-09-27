from WORLD.AI.action_executor import ActionExecutor
from WORLD.AI.decision import DecisionSystem
from WORLD.NPCs.npc import NPC
from WORLD.Shopping.shopping import ShoppingSystem
from WORLD.world import World
from WORLD.AI.action import ActionType

def create_npc(
    name="Rahul",
    role="farmer",
    location="House 1",
    hunger=85,
    energy=100,
    food=0,
    money=50,
) -> NPC:
    return NPC(
        name=name,
        role=role,
        money=money,
        home="House 1",
        location=location,
        hunger=hunger,
        energy=energy,
        food=food,
    )


def test_hungry_npc_buys_food():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)

    # Shopping is now state-driven, not hour-driven.
    world.clock.hour = 10

    ShoppingSystem().update(world)

    assert rahul.money == 45
    assert rahul.food == 1

    assert world.shop.money == 105
    assert world.shop.food == 19


def test_hungry_npc_can_shop_at_19():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)

    world.clock.hour = 19

    ShoppingSystem().update(world)

    assert rahul.money == 45
    assert rahul.food == 1

    assert world.shop.money == 105
    assert world.shop.food == 19


def test_npc_with_food_does_not_buy_again():
    world = World()

    rahul = create_npc(food=1)

    world.add_npc(rahul)

    world.clock.hour = 10

    ShoppingSystem().update(world)

    assert rahul.money == 50
    assert rahul.food == 1

    assert world.shop.money == 100
    assert world.shop.food == 20


def test_npc_without_enough_money_does_not_buy():
    world = World()

    rahul = create_npc(money=0)

    world.add_npc(rahul)

    world.clock.hour = 10

    ShoppingSystem().update(world)

    assert rahul.money == 0
    assert rahul.food == 0

    assert world.shop.money == 100
    assert world.shop.food == 20


def test_shopkeeper_does_not_buy_from_own_shop():
    world = World()

    ali = create_npc(
        name="Ali",
        role="shopkeeper",
        location="General Store",
    )

    world.add_npc(ali)

    world.clock.hour = 10

    ShoppingSystem().update(world)

    assert ali.money == 50
    assert ali.food == 0

    assert world.shop.money == 100
    assert world.shop.food == 20


def test_shopping_can_be_followed_by_eating():
    world = World()

    rahul = create_npc(
        hunger=85,
        energy=50,
        food=0,
    )

    world.add_npc(rahul)

    shopping = ShoppingSystem()
    shopping.update(world)

    assert rahul.food == 1
    assert rahul.money == 45

    # Now Rahul already owns food.
    # The next decision should be EAT.
    decision = world.decision_system.decide(rahul, world)

    from WORLD.AI.action import ActionType

    assert decision.chosen_action == ActionType.EAT


def test_high_food_price_can_block_shopping():
    world = World()

    rahul = create_npc(
        hunger=85,
        money=6,
        food=0,
    )

    world.add_npc(rahul)

    world.shop.food = 2

    world.pricing_system.update(world)

    assert world.shop.food_price == 8

    decision = world.decision_system.decide(
        rahul,
        world,
    )

    assert decision.scores.get(ActionType.SHOP, 0) == 0

