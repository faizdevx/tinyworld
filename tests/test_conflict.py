from WORLD.Conflict.conflict import ConflictSystem
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def create_npc(
    name,
    location="House 1",
    money=0,
    food=0,
    hunger=80,
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


def test_food_scarcity_creates_conflict():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert rahul.get_relationship(ali) == -5
    assert ali.get_relationship(rahul) == -5


def test_conflict_requires_food_scarcity():
    world = World()

    world.shop.food = 3
    world.shop.food_price = 5

    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0


def test_conflict_requires_same_location():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc(
        "Rahul",
        location="House 1",
    )

    ali = create_npc(
        "Ali",
        location="House 2",
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0


def test_conflict_requires_both_npcs_to_be_hungry():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc(
        "Rahul",
        hunger=80,
    )

    ali = create_npc(
        "Ali",
        hunger=40,
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0


def test_conflict_requires_both_npcs_to_lack_food():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc(
        "Rahul",
        food=0,
    )

    ali = create_npc(
        "Ali",
        food=1,
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0


def test_conflict_requires_both_npcs_to_be_unable_to_afford_food():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc(
        "Rahul",
        money=0,
    )

    ali = create_npc(
        "Ali",
        money=10,
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0


def test_conflict_creates_negative_memories():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert any(
        "Argued with Ali" in memory.event
        for memory in rahul.memories
    )

    assert any(
        "Argued with Rahul" in memory.event
        for memory in ali.memories
    )


def test_conflict_creates_world_event():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert len(world.event_log.events) == 1

    event = world.event_log.events[0]

    assert event.event_type == "CONFLICT"
    assert event.actor == "Rahul"
    assert event.target == "Ali"


def test_same_pair_only_conflicts_once_per_update():
    world = World()

    world.shop.food = 2
    world.shop.food_price = 8

    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    world.add_npc(rahul)
    world.add_npc(ali)

    ConflictSystem().update(world)

    assert len(world.event_log.events) == 1
    assert rahul.get_relationship(ali) == -5
    assert ali.get_relationship(rahul) == -5