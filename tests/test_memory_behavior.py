from types import SimpleNamespace

from WORLD.AI.experience_influence import ExperienceInfluence
from WORLD.AI.experience_reflection import ExperienceReflector
from WORLD.AI.knowledge import KnowledgeBase
from WORLD.AI.knowledge_extractor import KnowledgeExtractor
from WORLD.AI.utility import UtilityContext, UtilitySystem
from WORLD.NPCs.memory import Memory


def make_npc():
    return SimpleNamespace(
        name="Rahul",
        personality=SimpleNamespace(
            sociability=0.5,
            ambition=0.5,
            generosity=0.5,
        ),
        knowledge=KnowledgeBase(),
    )


def test_positive_social_experience_changes_behavior_score():
    npc = make_npc()
    utility = UtilitySystem()
    context = UtilityContext(social_need=50)

    baseline = utility.score_socialize(npc, context)
    npc.knowledge.add(
        subject="Ali",
        predicate="provides_help",
        value=True,
        confidence=0.9,
    )
    adjusted = utility.score_socialize_with_experience(
        npc,
        context,
        target="Ali",
    )

    assert adjusted > baseline


def test_negative_social_experience_changes_behavior_score():
    npc = make_npc()
    utility = UtilitySystem()
    context = UtilityContext(social_need=50)

    baseline = utility.score_socialize(npc, context)
    npc.knowledge.add(
        subject="Ali",
        predicate="provides_help",
        value=False,
        confidence=0.9,
    )
    adjusted = utility.score_socialize_with_experience(
        npc,
        context,
        target="Ali",
    )

    assert adjusted < baseline


def test_unrelated_knowledge_does_not_change_social_score():
    npc = make_npc()
    utility = UtilitySystem()
    context = UtilityContext(social_need=50)

    baseline = utility.score_socialize(npc, context)
    npc.knowledge.add(
        subject="Ali",
        predicate="provides_financial_credit",
        value=False,
        confidence=0.9,
    )
    adjusted = utility.score_socialize_with_experience(
        npc,
        context,
        target="Ali",
    )

    assert adjusted == baseline


def test_experience_can_flow_to_future_behavior():
    npc = make_npc()
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=0.9,
        participants=["Rahul", "Ali"],
    )
    reflection = ExperienceReflector().reflect(npc, memory)

    assert reflection is not None

    knowledge = KnowledgeExtractor().extract(npc, reflection)

    assert knowledge is not None
    assert knowledge.subject == "Ali"
    assert knowledge.predicate == "provides_help"
    assert knowledge.value is True

    utility = UtilitySystem()
    context = UtilityContext(social_need=50)
    before = utility.score_socialize(npc, context)
    npc.knowledge.add(
        subject=knowledge.subject,
        predicate=knowledge.predicate,
        value=knowledge.value,
        confidence=knowledge.confidence,
    )
    after = utility.score_socialize_with_experience(
        npc,
        context,
        target="Ali",
    )

    assert after > before


def test_experience_influence_is_deterministic_and_targeted():
    npc = make_npc()
    knowledge = KnowledgeBase()
    knowledge.add(
        subject="Ali",
        predicate="provides_help",
        value=True,
        confidence=0.9,
    )

    influences = ExperienceInfluence().influence(knowledge, target="Ali")

    assert len(influences) == 1
    assert influences[0].modifier == 20
    assert influences[0].action.name == "SOCIALIZE"
