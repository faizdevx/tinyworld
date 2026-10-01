from types import SimpleNamespace

from WORLD.AI.experience_reflection import ExperienceReflection
from WORLD.AI.knowledge_extractor import KnowledgeExtractor
from WORLD.NPCs.memory import Memory


def make_npc():
    return SimpleNamespace(name="Rahul")


def test_extracts_financial_credit_knowledge():
    memory = Memory(
        day=2,
        hour=12,
        event="Ali refused to lend Rahul money",
        importance=0.9,
        participants=["Rahul", "Ali"],
    )
    reflection = ExperienceReflection(
        memory=memory,
        observation=memory.event,
        interpretation="Ali refused support.",
        lesson="Consider an alternative person.",
        suggested_behavior="Ask someone else.",
    )

    knowledge = KnowledgeExtractor().extract(make_npc(), reflection)

    assert knowledge is not None
    assert knowledge.subject == "Ali"
    assert knowledge.predicate == "provides_financial_credit"
    assert knowledge.value is False
    assert knowledge.confidence == 0.9


def test_extracts_refusal_knowledge_from_rejection_event():
    memory = Memory(
        day=3,
        hour=8,
        event="Ali rejected Rahul's credit request",
        importance=0.8,
        participants=["Rahul", "Ali"],
    )
    reflection = ExperienceReflection(
        memory=memory,
        observation=memory.event,
        interpretation="Ali denied support.",
        lesson="Consider alternatives.",
        suggested_behavior="Find another lender.",
    )

    knowledge = KnowledgeExtractor().extract(make_npc(), reflection)

    assert knowledge is not None
    assert knowledge.subject == "Ali"
    assert knowledge.predicate == "provides_financial_credit"
    assert knowledge.value is False


def test_returns_none_for_uninformative_event():
    memory = Memory(
        day=4,
        hour=15,
        event="Worked at the farm",
        importance=0.7,
        participants=["Rahul"],
    )
    reflection = ExperienceReflection(
        memory=memory,
        observation=memory.event,
        interpretation="The event was routine.",
        lesson="It was ordinary.",
        suggested_behavior="Continue.",
    )

    knowledge = KnowledgeExtractor().extract(make_npc(), reflection)

    assert knowledge is None
