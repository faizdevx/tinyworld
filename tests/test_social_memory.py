from types import SimpleNamespace

import pytest

from WORLD.AI.brain import Brain
from WORLD.AI.knowledge import KnowledgeBase
from WORLD.AI.social_memory import SocialMemoryStore
from WORLD.NPCs.memory import Memory
from WORLD.NPCs.npc import NPC


def make_npc():
    return SimpleNamespace(name="Rahul")


def test_social_memory_records_other_participants():
    npc = make_npc()
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=0.8,
        participants=["Rahul", "Ali"],
    )
    store = SocialMemoryStore()

    store.record(npc, memory)

    assert store.for_person("Ali") == [memory]


def test_social_memory_does_not_index_npc_as_other_person():
    npc = make_npc()
    memory = Memory(
        day=1,
        hour=10,
        event="Rahul talked with Ali",
        importance=0.5,
        participants=["Rahul", "Ali"],
    )
    store = SocialMemoryStore()

    store.record(npc, memory)

    assert store.for_person("Rahul") == []
    assert store.for_person("Ali") == [memory]


def test_social_memory_keeps_multiple_interactions():
    npc = make_npc()
    first = Memory(
        day=1,
        hour=8,
        event="Ali helped Rahul",
        importance=0.8,
        participants=["Rahul", "Ali"],
    )
    second = Memory(
        day=2,
        hour=12,
        event="Rahul talked with Ali",
        importance=0.5,
        participants=["Rahul", "Ali"],
    )
    store = SocialMemoryStore()

    store.record(npc, first)
    store.record(npc, second)

    result = store.for_person("Ali")

    assert result == [second, first]


def test_social_memory_supports_limit():
    npc = make_npc()
    memories = [
        Memory(
            day=1,
            hour=hour,
            event=f"Talked with Ali {hour}",
            importance=0.5,
            participants=["Rahul", "Ali"],
        )
        for hour in range(3)
    ]
    store = SocialMemoryStore()

    for memory in memories:
        store.record(npc, memory)

    result = store.for_person("Ali", limit=2)

    assert len(result) == 2
    assert result[0] is memories[2]


def test_social_memory_rejects_invalid_limit():
    store = SocialMemoryStore()

    with pytest.raises(ValueError):
        store.for_person("Ali", limit=0)


def test_social_memory_lists_known_people():
    npc = make_npc()
    store = SocialMemoryStore()

    store.record(
        npc,
        Memory(
            day=1,
            hour=8,
            event="Talked with Ali",
            importance=0.5,
            participants=["Rahul", "Ali"],
        ),
    )
    store.record(
        npc,
        Memory(
            day=1,
            hour=9,
            event="Talked with Sara",
            importance=0.5,
            participants=["Rahul", "Sara"],
        ),
    )

    assert set(store.people()) == {"Ali", "Sara"}


def test_npc_remember_updates_social_memory():
    rahul = NPC(
        name="Rahul",
        role="worker",
        money=50,
        home="Home",
        location="Home",
    )
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=0.9,
        participants=["Rahul", "Ali"],
    )

    rahul.remember(memory)

    assert rahul.social_memory.for_person("Ali") == [memory]


def test_social_memory_respects_npc_memory_limit():
    rahul = NPC(
        name="Rahul",
        role="worker",
        money=50,
        home="Home",
        location="Home",
    )

    for index in range(rahul.MAX_MEMORIES + 1):
        rahul.remember(
            Memory(
                day=1,
                hour=index % 24,
                event=f"Talked with Ali {index}",
                importance=0.5,
                timestamp=index,
                participants=["Rahul", "Ali"],
            )
        )

    assert rahul.social_memory.count("Ali") == rahul.MAX_MEMORIES


def test_brain_retrieves_social_context():
    npc = SimpleNamespace(
        name="Rahul",
        memories=[],
        relationships={},
        social_memory=SocialMemoryStore(),
        knowledge=KnowledgeBase(),
    )
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=0.9,
        participants=["Rahul", "Ali"],
    )
    npc.social_memory.record(npc, memory)
    npc.knowledge.add(
        subject="Ali",
        predicate="provides_help",
        value=True,
        confidence=0.9,
    )

    brain = Brain(
        npc=npc,
        perception=None,
        goal_system=None,
        planner=None,
        replanner=None,
        memory_retriever=None,
        decision_system=None,
        action_executor=None,
    )

    context = brain.retrieve_social_context("Ali")

    assert context["person"] == "Ali"
    assert context["memories"][0] is memory
    assert len(context["knowledge"]) == 1
    assert context["relationship"] is None
