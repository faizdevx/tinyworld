from types import SimpleNamespace

import pytest

from WORLD.AI.memory_retrieval import MemoryRetriever
from WORLD.NPCs.memory import Memory


def make_npc(memories):
    return SimpleNamespace(
        memories=memories,
        relationships={},
        current_goal=None,
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


def test_retrieve_supports_limit():
    memories = [
        Memory(
            day=1,
            hour=8,
            event="Ali helped Rahul",
            importance=5,
        ),
        Memory(
            day=1,
            hour=9,
            event="Ali talked with Rahul",
            importance=4,
        ),
        Memory(
            day=1,
            hour=10,
            event="Ali visited Rahul",
            importance=3,
        ),
    ]

    npc = make_npc(memories)

    result = MemoryRetriever().retrieve(
        npc,
        "Ali",
        limit=2,
    )

    assert len(result) == 2


def test_retrieve_supports_minimum_importance():
    memories = [
        Memory(
            day=1,
            hour=8,
            event="Ali helped Rahul",
            importance=1,
        ),
        Memory(
            day=1,
            hour=9,
            event="Ali saved Rahul during famine",
            importance=8,
        ),
    ]

    npc = make_npc(memories)

    result = MemoryRetriever().retrieve(
        npc,
        "Ali",
        min_importance=5,
    )

    assert result == [memories[1]]


def test_retrieve_ranks_more_recent_memory_higher():
    older = Memory(
        day=1,
        hour=8,
        event="Ali helped Rahul",
        importance=1,
    )

    newer = Memory(
        day=1,
        hour=18,
        event="Ali helped Rahul",
        importance=1,
    )

    npc = make_npc(
        [
            older,
            newer,
        ]
    )

    result = MemoryRetriever().retrieve(
        npc,
        "Ali",
        current_timestamp=20,
        limit=2,
    )

    assert result[0] is newer


def test_retrieve_can_match_participants():
    memory = Memory(
        day=2,
        hour=10,
        event="Received food",
        importance=5,
        participants=["Ali"],
        location="General Store",
    )

    npc = make_npc([memory])

    result = MemoryRetriever().retrieve(
        npc,
        "Ali",
    )

    assert result == [memory]


def test_retrieve_can_rank_goal_relevant_memory():
    first = Memory(
        day=1,
        hour=8,
        event="Ali talked with Rahul",
        importance=5,
    )

    second = Memory(
        day=1,
        hour=9,
        event="Worked at the farm to earn money",
        importance=5,
    )

    goal = SimpleNamespace(
        goal_type=SimpleNamespace(
            value="earn_money",
        )
    )

    npc = SimpleNamespace(
        memories=[
            first,
            second,
        ],
        relationships={},
        current_goal=goal,
    )

    result = MemoryRetriever().retrieve(
        npc,
        "earn_money",
        limit=2,
    )

    assert result[0] is second


def test_retrieve_rejects_invalid_limit():
    npc = make_npc([])

    with pytest.raises(ValueError):
        MemoryRetriever().retrieve(
            npc,
            "Ali",
            limit=0,
        )


def test_retrieve_rejects_negative_minimum_importance():
    npc = make_npc([])

    with pytest.raises(ValueError):
        MemoryRetriever().retrieve(
            npc,
            "Ali",
            min_importance=-1,
        )