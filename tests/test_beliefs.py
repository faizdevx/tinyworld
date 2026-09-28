import pytest

from WORLD.AI.beliefs import Belief


def test_belief_stores_subject():
    belief = Belief(
        subject="Ali",
        predicate="trustworthy",
        value=True,
        confidence=0.9,
    )

    assert belief.subject == "Ali"


def test_belief_stores_predicate():
    belief = Belief(
        subject="Ali",
        predicate="trustworthy",
        value=True,
        confidence=0.9,
    )

    assert belief.predicate == "trustworthy"


def test_belief_stores_value():
    belief = Belief(
        subject="Shop",
        predicate="has_food",
        value=True,
        confidence=1.0,
    )

    assert belief.value is True


def test_belief_stores_confidence():
    belief = Belief(
        subject="Shop",
        predicate="food_price",
        value=5,
        confidence=0.8,
    )

    assert belief.confidence == 0.8


@pytest.mark.parametrize("confidence", [-0.1, 1.1, 2.0])
def test_belief_rejects_invalid_confidence(confidence):
    with pytest.raises(ValueError):
        Belief(
            subject="Ali",
            predicate="trustworthy",
            value=True,
            confidence=confidence,
        )


def test_belief_requires_subject():
    with pytest.raises(ValueError):
        Belief(
            subject="",
            predicate="trustworthy",
            value=True,
            confidence=0.9,
        )


def test_belief_requires_predicate():
    with pytest.raises(ValueError):
        Belief(
            subject="Ali",
            predicate="",
            value=True,
            confidence=0.9,
        )