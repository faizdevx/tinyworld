from types import SimpleNamespace

from WORLD.AI.personality import Personality
from WORLD.AI.utility import UtilityContext, UtilitySystem


def make_npc(
    *,
    risk_tolerance=0.5,
    sociability=0.5,
    generosity=0.5,
    ambition=0.5,
    patience=0.5,
):
    return SimpleNamespace(
        personality=Personality(
            risk_tolerance=risk_tolerance,
            sociability=sociability,
            generosity=generosity,
            ambition=ambition,
            patience=patience,
        )
    )


def test_sociability_affects_socialize_score():
    context = UtilityContext(
        social_need=100,
    )

    social_npc = make_npc(
        sociability=0.9,
    )

    quiet_npc = make_npc(
        sociability=0.2,
    )

    utility = UtilitySystem()

    assert (
        utility.score_socialize(social_npc, context)
        == 90
    )

    assert (
        utility.score_socialize(quiet_npc, context)
        == 20
    )


def test_ambition_affects_work_score():
    context = UtilityContext(
        money_need=100,
    )

    ambitious_npc = make_npc(
        ambition=0.9,
    )

    unambitious_npc = make_npc(
        ambition=0.2,
    )

    utility = UtilitySystem()

    assert (
        utility.score_work(ambitious_npc, context)
        == 90
    )

    assert (
        utility.score_work(unambitious_npc, context)
        == 20
    )


def test_generosity_affects_helping_score():
    context = UtilityContext(
        relationship_strength=100,
    )

    generous_npc = make_npc(
        generosity=0.9,
    )

    selfish_npc = make_npc(
        generosity=0.2,
    )

    utility = UtilitySystem()

    assert (
        utility.score_helping(generous_npc, context)
        == 90
    )

    assert (
        utility.score_helping(selfish_npc, context)
        == 20
    )


def test_same_context_can_produce_different_social_scores():
    context = UtilityContext(
        social_need=80,
    )

    npc_a = make_npc(
        sociability=0.25,
    )

    npc_b = make_npc(
        sociability=0.75,
    )

    utility = UtilitySystem()

    score_a = utility.score_socialize(
        npc_a,
        context,
    )

    score_b = utility.score_socialize(
        npc_b,
        context,
    )

    assert score_a == 20
    assert score_b == 60
    assert score_a != score_b


def test_zero_personality_factor_produces_zero_score():
    context = UtilityContext(
        social_need=100,
        money_need=100,
        relationship_strength=100,
    )

    npc = make_npc(
        sociability=0.0,
        ambition=0.0,
        generosity=0.0,
    )

    utility = UtilitySystem()

    assert utility.score_socialize(npc, context) == 0
    assert utility.score_work(npc, context) == 0
    assert utility.score_helping(npc, context) == 0