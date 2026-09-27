from WORLD.NPCs.npc import NPC
from WORLD.Buildings.buildings import Building
from WORLD.Economy.money import transfer_money, total_money
from WORLD.Map.position import Position
from WORLD.Resources.food import Resource


def test_basic_village_simulation():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=2,
    )

    shop = Building(
        name="General Store",
        building_type="shop",
        money=100,
    )

    food = Resource(
        name="Food",
        quantity=100,
    )

    farm_position = Position(2, 2)
    shop_position = Position(5, 3)

    # Rahul moves to the farm.
    rahul.move_to("Village Farm", farm_position)

    assert rahul.location == "Village Farm"
    assert rahul.position == farm_position

    # Rahul buys something from the shop.
    before_money = total_money([rahul, shop])

    assert transfer_money(rahul, shop, 5) is True

    after_money = total_money([rahul, shop])

    # Money conservation.
    assert before_money == after_money

    # Rahul eats.
    assert rahul.eat() is True
    assert rahul.food == 1

    # Village food resource changes.
    assert food.consume(10) is True
    assert food.quantity == 90

    # Map still works.
    assert farm_position.manhattan_distance_to(shop_position) == 4