from WORLD.NPCs.npc import NPC
from WORLD.Work.work import WorkSystem
from WORLD.world import World


def create_npc(
    location="Village Farm",
    energy=80,
    hunger=20,
    food=0,
    money=50,
) -> NPC:
    return NPC(
        name="Rahul",
        role="farmer",
        money=money,
        home="House 1",
        location=location,
        energy=energy,
        hunger=hunger,
        food=food,
    )


def test_npc_works_when_work_is_the_best_action():
    world = World()

    rahul = create_npc(
        location="Village Farm",
        energy=80,
        hunger=20,
    )

    world.add_npc(rahul)

    WorkSystem().update(world)

    assert rahul.energy == 75
    assert rahul.location == "Village Farm"


def test_low_energy_npc_chooses_sleep_instead_of_work():
    world = World()

    rahul = create_npc(
        location="Village Farm",
        energy=20,
        hunger=20,
    )

    world.add_npc(rahul)

    WorkSystem().update(world)

    # The schedule placed Rahul at work,
    # but his state made SLEEP the better action.
    assert rahul.location == "House 1"
    assert rahul.energy == 35


def test_npc_at_home_does_not_work():
    world = World()

    rahul = create_npc(
        location="House 1",
        energy=80,
        hunger=20,
    )

    world.add_npc(rahul)

    WorkSystem().update(world)

    assert rahul.energy == 80
    assert rahul.location == "House 1"