from WORLD.AI.personality import Personality


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