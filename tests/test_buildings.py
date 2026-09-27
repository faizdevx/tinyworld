import pytest

from WORLD.Buildings.buildings import Building


def test_building_creation():
    shop = Building(
        name="General Store",
        building_type="shop",
        money=100
    )

    assert shop.name == "General Store"
    assert shop.building_type == "shop"
    assert shop.money == 100


def test_building_can_receive_money():
    shop = Building(
        name="General Store",
        building_type="shop",
        money=100
    )

    shop.add_money(25)

    assert shop.money == 125


def test_negative_building_money_is_rejected():
    with pytest.raises(ValueError):
        Building(
            name="Broken Shop",
            building_type="shop",
            money=-1
        )