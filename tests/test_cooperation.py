from WORLD.Cooperation.cooperation import CooperationSystem
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def create_npc(
    name,
    money=0,
    food=0,
    hunger=80,
    location="House 1",
):
    return NPC(
        name=name,
        role="worker",
        money=money,
        home="House 1",
        location=location,
        food=food,
        hunger=hunger,
    )


def test_friend_can_give_food_to_hungry_npc():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=0,
        food=0,
        hunger=80,
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        30,
    )

    CooperationSystem().update(world)

    assert receiver.food == 1
    assert donor.food == 1


def test_cooperation_requires_strong_relationship():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=0,
        food=0,
        hunger=80,
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        29,
    )

    CooperationSystem().update(world)

    assert receiver.food == 0
    assert donor.food == 2


def test_cooperation_requires_same_location():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=0,
        food=0,
        hunger=80,
        location="House 1",
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
        location="House 2",
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        50,
    )

    CooperationSystem().update(world)

    assert receiver.food == 0
    assert donor.food == 2


def test_cooperation_does_not_happen_when_receiver_can_afford_food():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=10,
        food=0,
        hunger=80,
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        50,
    )

    CooperationSystem().update(world)

    assert receiver.food == 0
    assert donor.food == 2


def test_cooperation_improves_relationship():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=0,
        food=0,
        hunger=80,
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        30,
    )

    CooperationSystem().update(world)

    assert receiver.get_relationship(donor) == 31
    assert donor.get_relationship(receiver) == 1


def test_cooperation_creates_memories():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=0,
        food=0,
        hunger=80,
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        30,
    )

    CooperationSystem().update(world)

    assert any(
        "Received food from Rahul" in memory.event
        for memory in receiver.memories
    )

    assert any(
        "Gave food to Sara" in memory.event
        for memory in donor.memories
    )


def test_cooperation_creates_world_event():
    world = World()

    receiver = create_npc(
        name="Sara",
        money=0,
        food=0,
        hunger=80,
    )

    donor = create_npc(
        name="Rahul",
        money=50,
        food=2,
        hunger=20,
    )

    world.add_npc(receiver)
    world.add_npc(donor)

    receiver.change_relationship(
        donor,
        30,
    )

    CooperationSystem().update(world)

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "FOOD_GIFT"
    assert event.actor == "Rahul"
    assert event.target == "Sara"