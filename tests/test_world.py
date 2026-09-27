from WORLD.world import World
from WORLD.NPCs.npc import NPC
from WORLD.Buildings.buildings import Building


def test_world_creation():
    world = World()

    assert world.clock is not None
    assert world.npcs == []
    assert world.buildings == []

    assert world.food.name == "Food"
    assert world.food.quantity == 100

    assert world.shop.name == "General Store"
    assert world.shop.money == 100
    assert world.shop.food == 20

    assert world.schedule_system is not None
    assert world.farming_system is not None
    assert world.needs_system is not None


def test_world_can_add_npc():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(rahul)

    assert len(world.npcs) == 1
    assert world.npcs[0] is rahul


def test_world_can_add_building():
    world = World()

    farm = Building(
        name="Village Farm",
        building_type="farm",
    )

    world.add_building(farm)

    assert len(world.buildings) == 1
    assert world.buildings[0] is farm