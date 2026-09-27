from WORLD.Buildings.shop import Shop
from WORLD.Economy.pricing import PricingSystem
from WORLD.world import World


def test_abundant_food_has_normal_price():
    shop = Shop(
        name="General Store",
        money=100,
        food=20,
        food_price=5,
    )

    pricing = PricingSystem()

    assert pricing.calculate_food_price(shop) == 5


def test_low_food_increases_price():
    shop = Shop(
        name="General Store",
        money=100,
        food=5,
        food_price=5,
    )

    pricing = PricingSystem()

    assert pricing.calculate_food_price(shop) == 6


def test_very_low_food_has_critical_price():
    shop = Shop(
        name="General Store",
        money=100,
        food=2,
        food_price=5,
    )

    pricing = PricingSystem()

    assert pricing.calculate_food_price(shop) == 8


def test_empty_shop_has_critical_price():
    shop = Shop(
        name="General Store",
        money=100,
        food=0,
        food_price=5,
    )

    pricing = PricingSystem()

    assert pricing.calculate_food_price(shop) == 8


def test_pricing_system_updates_world_price():
    world = World()

    world.shop.food = 5

    world.pricing_system.update(world)

    assert world.shop.food_price == 6


def test_pricing_system_returns_to_normal_when_supply_recovers():
    world = World()

    world.shop.food = 2

    world.pricing_system.update(world)

    assert world.shop.food_price == 8

    world.shop.food = 20

    world.pricing_system.update(world)

    assert world.shop.food_price == 5