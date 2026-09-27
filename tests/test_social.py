from WORLD.NPCs.npc import NPC
from WORLD.Social.social import SocialSystem
from WORLD.world import World


def create_npc(name: str, location: str) -> NPC:
    return NPC(
        name=name,
        role="worker",
        money=50,
        home="House 1",
        location=location,
    )


def test_same_location_creates_interaction():
    world = World()

    rahul = create_npc("Rahul", "House 1")
    ali = create_npc("Ali", "House 1")

    world.add_npc(rahul)
    world.add_npc(ali)

    world.clock.hour = 12

    social = SocialSystem()
    social.update(world)

    assert rahul.get_relationship(ali) == 1
    assert ali.get_relationship(rahul) == 1

    assert len(rahul.memories) == 1
    assert len(ali.memories) == 1


def test_different_locations_do_not_interact():
    world = World()

    rahul = create_npc("Rahul", "House 1")
    ali = create_npc("Ali", "House 2")

    world.add_npc(rahul)
    world.add_npc(ali)

    world.clock.hour = 12

    social = SocialSystem()
    social.update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0

    assert len(rahul.memories) == 0
    assert len(ali.memories) == 0


def test_social_interaction_requires_social_decision():
    world = World()

    rahul = create_npc("Rahul", "House 1")
    ali = create_npc("Ali", "House 2")

    world.add_npc(rahul)
    world.add_npc(ali)

    # Make Rahul exhausted.
    # DecisionSystem should prefer SLEEP.
    rahul.energy = 20
    rahul.hunger = 20

    world.social_system.update(world)

    assert rahul.get_relationship(ali) == 0
    assert ali.get_relationship(rahul) == 0

    assert len(rahul.memories) == 0
    assert len(ali.memories) == 0