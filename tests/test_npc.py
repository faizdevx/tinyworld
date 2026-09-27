import pytest

from WORLD.NPCs.npc import NPC
from WORLD.Map.position import Position


def test_npc_creation():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1"
    )

    assert npc.name == "Rahul"
    assert npc.role == "farmer"
    assert npc.money == 50
    assert npc.energy == 100
    assert npc.food == 0


def test_npc_can_move():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1"
    )

    farm_position = Position(2, 2)

    npc.move_to("Village Farm", farm_position)

    assert npc.location == "Village Farm"
    assert npc.position == farm_position


def test_npc_can_eat():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=3,
        energy=50
    )

    assert npc.eat() is True

    assert npc.food == 2
    assert npc.energy == 70


def test_npc_cannot_eat_without_food():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1"
    )

    assert npc.eat() is False
    assert npc.food == 0
    assert npc.energy == 100


def test_energy_never_goes_above_100():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=90
    )

    npc.restore_energy(50)

    assert npc.energy == 100


def test_npc_has_hunger():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        hunger=30,
    )

    assert npc.hunger == 30


def test_npc_has_hunger():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        hunger=30,
    )

    assert npc.hunger == 30

def test_eating_reduces_hunger_and_restores_energy():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        food=1,
        hunger=70,
        energy=50,
    )

    result = npc.eat()

    assert result is True
    assert npc.food == 0
    assert npc.hunger == 30
    assert npc.energy == 70


def test_productivity_is_reduced_at_low_energy():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=20,
    )

    assert npc.productivity == 0.5


def test_productivity_is_reduced_at_low_energy():
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        energy=20,
    )

    assert npc.productivity == 0.5


