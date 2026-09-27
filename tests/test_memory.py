from WORLD.NPCs.memory import Memory
from WORLD.NPCs.npc import NPC


def create_npc() -> NPC:
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )


def test_npc_can_remember_event():
    rahul = create_npc()

    memory = Memory(
        day=3,
        hour=14,
        event="Ali helped Rahul",
        importance=5,
    )

    rahul.remember(memory)

    assert len(rahul.memories) == 1
    assert rahul.memories[0].event == "Ali helped Rahul"
    assert rahul.memories[0].day == 3
    assert rahul.memories[0].hour == 14


def test_memory_limit_removes_oldest_memory():
    rahul = create_npc()

    for i in range(51):
        rahul.remember(
            Memory(
                day=1,
                hour=i % 24,
                event=f"Event {i}",
                importance=1,
            )
        )

    assert len(rahul.memories) == 50
    assert rahul.memories[0].event == "Event 1"
    assert rahul.memories[-1].event == "Event 50"