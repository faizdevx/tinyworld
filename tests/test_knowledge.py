import pytest

from WORLD.AI.knowledge import Knowledge


def test_knowledge_validates_fields():
    knowledge = Knowledge(
        subject="Ali",
        predicate="provides_help",
        value=True,
        confidence=0.8,
    )
    assert knowledge.subject == "Ali"
    assert knowledge.predicate == "provides_help"
    assert knowledge.value is True
    assert knowledge.confidence == 0.8
    assert knowledge.evidence_count == 1


def test_knowledge_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        Knowledge(
            subject="Ali",
            predicate="provides_help",
            value=True,
            confidence=1.1,
        )
    with pytest.raises(ValueError):
        Knowledge(
            subject="Ali",
            predicate="provides_help",
            value=True,
            confidence=-0.1,
        )


def test_knowledge_rejects_empty_subject():
    with pytest.raises(ValueError):
        Knowledge(
            subject="   ",
            predicate="provides_help",
            value=True,
            confidence=0.8,
        )


def test_knowledge_rejects_empty_predicate():
    with pytest.raises(ValueError):
        Knowledge(
            subject="Ali",
            predicate="   ",
            value=True,
            confidence=0.8,
        )


def test_knowledge_rejects_invalid_evidence_count():
    with pytest.raises(ValueError):
        Knowledge(
            subject="Ali",
            predicate="provides_help",
            value=True,
            confidence=0.8,
            evidence_count=0,
        )


def test_knowledge_accepts_evidence_count():
    knowledge = Knowledge(
        subject="Ali",
        predicate="provides_help",
        value=False,
        confidence=0.9,
        evidence_count=3,
    )
    assert knowledge.evidence_count == 3
