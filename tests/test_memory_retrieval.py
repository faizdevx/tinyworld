from types import SimpleNamespace

from WORLD.AI.memory_retrieval import MemoryRetriever
from WORLD.NPCs.memory import Memory


def make_npc(memories):
    return SimpleNamespace(
        memories=memories,
    )


def test_retrieves_matching_memory():
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=2,
    )

    npc = make_npc([memory])

    result = MemoryRetriever().relevant_memories(
        npc,
        "Ali",
    )

    assert result == [memory]


def test_retrieval_is_case_insensitive():
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=2,
    )

    npc = make_npc([memory])

    result = MemoryRetriever().relevant_memories(
        npc,
        "ali",
    )

    assert result == [memory]


def test_non_matching_memory_is_not_returned():
    memory = Memory(
        day=1,
        hour=10,
        event="Worked at the farm",
        importance=1,
    )

    npc = make_npc([memory])

    result = MemoryRetriever().relevant_memories(
        npc,
        "Ali",
    )

    assert result == []


def test_multiple_matching_memories_are_returned():
    memory_one = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=2,
    )

    memory_two = Memory(
        day=2,
        hour=15,
        event="Talked with Ali at the shop",
        importance=1,
    )

    memory_three = Memory(
        day=2,
        hour=8,
        event="Worked at the farm",
        importance=1,
    )

    npc = make_npc(
        [
            memory_one,
            memory_two,
            memory_three,
        ]
    )

    result = MemoryRetriever().relevant_memories(
        npc,
        "Ali",
    )

    assert result == [
        memory_one,
        memory_two,
    ]


def test_empty_topic_returns_no_memories():
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=2,
    )

    npc = make_npc([memory])

    result = MemoryRetriever().relevant_memories(
        npc,
        "",
    )

    assert result == []


def test_empty_memory_list_returns_no_results():
    npc = make_npc([])

    result = MemoryRetriever().relevant_memories(
        npc,
        "Ali",
    )

    assert result == []