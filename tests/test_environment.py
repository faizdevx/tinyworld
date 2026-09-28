from WORLD.Farming.farming import FarmingSystem
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def create_farmer():
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
    )


def test_drought_starts_inactive():
    world = World()

    assert world.environment_system.drought_active is False
    assert (
        world.environment_system.production_multiplier()
        == 1.0
    )


def test_drought_changes_production_multiplier():
    world = World()

    world.environment_system.start_drought(world)

    assert world.environment_system.drought_active is True
    assert (
        world.environment_system.production_multiplier()
        == 0.5
    )


def test_drought_reduces_farmer_production():
    world = World(seed=42)
    world.clock.hour = 12

    farmer = create_farmer()
    world.add_npc(farmer)

    world.environment_system.start_drought(world)

    before = world.food.quantity

    FarmingSystem().update(world)

    produced = world.food.quantity - before

    assert produced in {0, 1, 2}


def test_drought_can_end():
    world = World()

    world.environment_system.start_drought(world)
    world.environment_system.end_drought(world)

    assert world.environment_system.drought_active is False
    assert (
        world.environment_system.production_multiplier()
        == 1.0
    )


def test_drought_creates_events():
    world = World()

    world.environment_system.start_drought(world)

    assert len(world.event_log.events) == 1
    assert (
        world.event_log.events[0].event_type
        == "DROUGHT_STARTED"
    )

    world.environment_system.end_drought(world)

    assert len(world.event_log.events) == 2
    assert (
        world.event_log.events[1].event_type
        == "DROUGHT_ENDED"
    )