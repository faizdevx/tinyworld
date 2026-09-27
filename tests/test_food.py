import pytest

from WORLD.Resources.food import Resource


def test_food_creation():
    food = Resource("Food", 100)

    assert food.name == "Food"
    assert food.quantity == 100


def test_food_can_be_added():
    food = Resource("Food", 100)

    food.add(25)

    assert food.quantity == 125


def test_food_can_be_consumed():
    food = Resource("Food", 100)

    result = food.consume(30)

    assert result is True
    assert food.quantity == 70


def test_food_cannot_go_negative():
    food = Resource("Food", 100)

    result = food.consume(200)

    assert result is False
    assert food.quantity == 100