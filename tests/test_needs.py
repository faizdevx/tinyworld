from WORLD.NPCs.npc import NPC
from WORLD.Needs.needs import NeedsSystem
from WORLD.world import World


def create_npc(
    hunger=60,
    energy=50,
    food=1,
    money=50,
) -> NPC:
    return NPC(
        name="Rahul",
        role="farmer",
        money=money,
        home="House 1",
        location="House 1",
        hunger=hunger,
        energy=energy,
        food=food,
    )


def test_hungry_npc_eats_when_food_is_available():
    world = World()

    rahul = create_npc(
        hunger=60,
        energy=50,
        food=1,
    )

    world.add_npc(rahul)

    # Deliberately not 20:00.
    world.clock.hour = 10

    NeedsSystem().update(world)

    # Hunger first increases:
    # 60 -> 64
    #
    # Then the decision system chooses EAT.
    # Eating reduces hunger by 40.
    assert rahul.hunger == 24
    assert rahul.food == 0
    assert rahul.energy == 70


def test_hungry_npc_does_not_eat_without_food():
    world = World()

    rahul = create_npc(
        hunger=70,
        energy=50,
        food=0,
        money=0,
    )

    world.add_npc(rahul)

    world.clock.hour = 10

    NeedsSystem().update(world)

    # Hunger increases first:
    # 70 -> 74
    #
    # No food exists, so EAT is unavailable.
    assert rahul.food == 0
    assert rahul.hunger == 74

    # Because hunger is >= 70 and the NPC could not eat,
    # energy takes a penalty.
    assert rahul.energy == 45

def test_needs_system_executes_decided_eat_action():
    world = World()

    rahul = create_npc(
        hunger=80,
        energy=50,
        food=1,
    )

    world.add_npc(rahul)

    world.clock.hour = 15

    NeedsSystem().update(world)

    assert rahul.food == 0
    assert rahul.hunger == 44
    assert rahul.energy == 70