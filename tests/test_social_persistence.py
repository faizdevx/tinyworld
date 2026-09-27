from WORLD.NPCs.npc import NPC
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


def test_social_state_persists_across_days():
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
        home="House 2",
        location="House 1",
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    # Keep both NPCs at the same location for every hour.
    for hour in range(24):
        rahul.schedule[hour] = "House 1"
        ali.schedule[hour] = "House 1"

    simulation = Simulation(world)

    # Village/World clock starts at Day 1, 08:00.
    assert world.clock.day == 1
    assert world.clock.hour == 8

    # ---------------------------------------------------------
    # DAY 1
    # ---------------------------------------------------------

    simulation.run(24)

    # One complete day has passed.
    assert world.clock.day == 2
    assert world.clock.hour == 8

    # They interacted, so their relationship should now be positive.
    assert rahul.get_relationship(ali) > 0
    assert ali.get_relationship(rahul) > 0

    # They should have memories of interacting.
    assert len(rahul.memories) > 0
    assert len(ali.memories) > 0

    # At least one memory should belong to Day 1.
    assert any(memory.day == 1 for memory in rahul.memories)
    assert any(memory.day == 1 for memory in ali.memories)

    relationship_after_day_1 = rahul.get_relationship(ali)
    memories_after_day_1 = len(rahul.memories)

    # ---------------------------------------------------------
    # DAY 2
    # ---------------------------------------------------------

    simulation.run(24)

    assert world.clock.day == 3
    assert world.clock.hour == 8

    # Relationship persists and continues changing.
    assert rahul.get_relationship(ali) > relationship_after_day_1

    # New memories are created on Day 2.
    assert len(rahul.memories) > memories_after_day_1

    assert any(memory.day == 2 for memory in rahul.memories)
    assert any(memory.day == 2 for memory in ali.memories)