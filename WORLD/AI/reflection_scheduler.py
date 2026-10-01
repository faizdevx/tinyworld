from dataclasses import dataclass

from WORLD.NPCs.memory import Memory


@dataclass(frozen=True)
class ReflectionDecision:
    should_reflect: bool
    reason: str


class ReflectionScheduler:
    """
    Determines whether a memory deserves experience reflection.
    """

    IMPORTANT_THRESHOLD = 0.5
    CRITICAL_THRESHOLD = 0.85

    def should_reflect(self, memory: Memory) -> ReflectionDecision:
        if memory.importance >= self.CRITICAL_THRESHOLD:
            return ReflectionDecision(
                should_reflect=True,
                reason="critical_experience",
            )
        if memory.importance >= self.IMPORTANT_THRESHOLD:
            return ReflectionDecision(
                should_reflect=True,
                reason="important_experience",
            )
        return ReflectionDecision(
            should_reflect=False,
            reason="routine_experience",
        )
