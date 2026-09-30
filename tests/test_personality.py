import pytest

from WORLD.AI.personality import Personality
from WORLD.NPCs.npc import NPC


def test_personality_stores_risk_tolerance():
    personality = Personality(
        risk_tolerance=0.2,
        sociability=0.5,
        generosity=0.8,
        ambition=0.4,
        patience=0.6,
    )

    assert personality.risk_tolerance == 0.2


def test_personality_stores_sociability():
    personality = Personality(
        risk_tolerance=0.2,
        sociability=0.9,
        generosity=0.8,
        ambition=0.4,
        patience=0.6,
    )

    assert personality.sociability == 0.9


def test_personality_stores_generosity():
    personality = Personality(
        risk_tolerance=0.2,
        sociability=0.5,
        generosity=0.8,
        ambition=0.4,
        patience=0.6,
    )

    assert personality.generosity == 0.8


def test_personality_stores_ambition():
    personality = Personality(
        risk_tolerance=0.2,
        sociability=0.5,
        generosity=0.8,
        ambition=0.9,
        patience=0.6,
    )

    assert personality.ambition == 0.9


def test_personality_stores_patience():
    personality = Personality(
        risk_tolerance=0.2,
        sociability=0.5,
        generosity=0.8,
        ambition=0.4,
        patience=0.9,
    )

    assert personality.patience == 0.9


def test_different_personalities_can_exist():
    ambitious = Personality(
        risk_tolerance=0.7,
        sociability=0.3,
        generosity=0.3,
        ambition=0.9,
        patience=0.4,
    )

    social = Personality(
        risk_tolerance=0.3,
        sociability=0.9,
        generosity=0.8,
        ambition=0.4,
        patience=0.7,
    )

    assert ambitious != social
    assert ambitious.ambition > social.ambition
    assert social.sociability > ambitious.sociability


def test_default_personality_is_valid():
    personality = Personality()

    assert personality.risk_tolerance == 0.5
    assert personality.sociability == 0.5
    assert personality.generosity == 0.5
    assert personality.ambition == 0.5
    assert personality.patience == 0.5


def test_personality_values_must_be_between_zero_and_one():
    with pytest.raises(ValueError):
        Personality(sociability=-0.1)

    with pytest.raises(ValueError):
        Personality(ambition=1.1)


def test_npc_has_independent_default_personality():
    first = NPC(
        name="Rahul",
        role="worker",
        money=50,
        home="Home",
        location="Home",
    )

    second = NPC(
        name="Ali",
        role="worker",
        money=50,
        home="Home",
        location="Home",
    )

    assert isinstance(first.personality, Personality)
    assert isinstance(second.personality, Personality)
    assert first.personality is not second.personality


def test_npc_accepts_explicit_personality():
    personality = Personality(
        risk_tolerance=0.2,
        sociability=0.9,
        generosity=0.8,
        ambition=0.4,
        patience=0.7,
    )

    npc = NPC(
        name="Sara",
        role="worker",
        money=50,
        home="Home",
        location="Home",
        personality=personality,
    )

    assert npc.personality is personality
    assert npc.personality.sociability == 0.9
    assert npc.personality.generosity == 0.8
