from WORLD.Events.event import WorldEvent
from WORLD.Events.event_log import EventLog
from WORLD.Farming.farming import FarmingSystem
from WORLD.Restocking.restocking import RestockingSystem
from WORLD.Social.social import SocialSystem
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def test_world_event_creation():
    event = WorldEvent(
        day=1,
        hour=12,
        event_type="FOOD_SHORTAGE",
        actor="Village",
        target=None,
        description="Village food storage is critically low.",
    )

    assert event.day == 1
    assert event.hour == 12
    assert event.event_type == "FOOD_SHORTAGE"
    assert event.actor == "Village"
    assert event.target is None


def test_event_log_stores_events():
    log = EventLog()

    event = WorldEvent(
        day=1,
        hour=12,
        event_type="HARVEST",
        actor="Village",
        target=None,
        description="Farm produced food.",
    )

    log.add(event)

    assert len(log.events) == 1
    assert log.events[0] == event


def test_farming_creates_event():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
    )

    world.add_npc(rahul)

    world.clock.hour = 12

    FarmingSystem().update(world)

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "HARVEST"
    assert event.target is None


def test_restocking_creates_event():
    world = World()

    world.clock.hour = 13

    RestockingSystem().update(world)

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "RESTOCK"
    assert event.target == world.shop.name


def test_social_interaction_creates_event():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )

    ali = NPC(
        name="Ali",
        role="shopkeeper",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    world.clock.hour = 10

    SocialSystem().interact(
        rahul,
        ali,
        world,
    )

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "SOCIALIZE"
    assert event.actor == "Rahul"
    assert event.target == "Ali"