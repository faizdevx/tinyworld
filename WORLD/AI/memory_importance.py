from dataclasses import dataclass


@dataclass(frozen=True)
class ImportanceContext:
    """
    Factors contributing to an experience's importance.

    Every factor is normalized to [0.0, 1.0].
    """

    emotional_significance: float = 0.0
    goal_relevance: float = 0.0
    novelty: float = 0.0
    social_significance: float = 0.0
    consequence: float = 0.0

    def __post_init__(self) -> None:
        values = {
            "emotional_significance": self.emotional_significance,
            "goal_relevance": self.goal_relevance,
            "novelty": self.novelty,
            "social_significance": self.social_significance,
            "consequence": self.consequence,
        }

        for name, value in values.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{name} must be between 0.0 and 1.0."
                )


class MemoryImportanceScorer:
    """
    Deterministically converts importance factors into
    a normalized memory importance score.
    """

    def score(
        self,
        context: ImportanceContext,
    ) -> float:
        return (
            context.emotional_significance
            + context.goal_relevance
            + context.novelty
            + context.social_significance
            + context.consequence
        ) / 5.0