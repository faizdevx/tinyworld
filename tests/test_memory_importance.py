import pytest

from WORLD.AI.memory_importance import (
    ImportanceContext,
    MemoryImportanceScorer,
)


def test_importance_context_defaults_to_zero():
    context = ImportanceContext()

    assert context.emotional_significance == 0.0
    assert context.goal_relevance == 0.0
    assert context.novelty == 0.0
    assert context.social_significance == 0.0
    assert context.consequence == 0.0


def test_importance_context_rejects_out_of_range_values():
    factor_names = (
        "emotional_significance",
        "goal_relevance",
        "novelty",
        "social_significance",
        "consequence",
    )

    for factor_name in factor_names:
        with pytest.raises(ValueError):
            ImportanceContext(**{factor_name: -0.1})

        with pytest.raises(ValueError):
            ImportanceContext(**{factor_name: 1.1})


def test_importance_score_is_zero_for_no_significance():
    context = ImportanceContext()

    score = MemoryImportanceScorer().score(context)

    assert score == 0.0


def test_importance_score_is_one_for_maximum_significance():
    context = ImportanceContext(
        emotional_significance=1.0,
        goal_relevance=1.0,
        novelty=1.0,
        social_significance=1.0,
        consequence=1.0,
    )

    score = MemoryImportanceScorer().score(context)

    assert score == 1.0


def test_importance_score_combines_all_factors():
    context = ImportanceContext(
        emotional_significance=0.8,
        goal_relevance=0.6,
        novelty=0.4,
        social_significance=1.0,
        consequence=0.2,
    )

    score = MemoryImportanceScorer().score(context)

    assert score == pytest.approx(0.6)


def test_significant_experience_scores_higher_than_routine_event():
    scorer = MemoryImportanceScorer()

    routine = scorer.score(
        ImportanceContext(
            emotional_significance=0.0,
            goal_relevance=0.1,
            novelty=0.0,
            social_significance=0.0,
            consequence=0.1,
        )
    )

    significant = scorer.score(
        ImportanceContext(
            emotional_significance=0.9,
            goal_relevance=0.8,
            novelty=0.8,
            social_significance=0.9,
            consequence=1.0,
        )
    )

    assert significant > routine