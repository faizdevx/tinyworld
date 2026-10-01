from dataclasses import dataclass

from WORLD.NPCs.memory import Memory


@dataclass(frozen=True)
class ExperienceReflection:
    """
    Structured interpretation of an important experience.

    This component is read-only. It does not mutate the NPC,
    memory store, beliefs, goals, or world.
    """

    memory: Memory
    observation: str
    interpretation: str
    lesson: str
    suggested_behavior: str


class ExperienceReflector:
    """
    Deterministic experience-reflection component.

    The current implementation uses simple structured rules.
    More sophisticated reflection can replace the internals later
    without changing the public interface.
    """

    REFLECTION_THRESHOLD = 0.5

    def reflect(
        self,
        npc,
        memory: Memory,
        *,
        current_goal: str | None = None,
    ) -> ExperienceReflection | None:
        if memory.importance < self.REFLECTION_THRESHOLD:
            return None

        event = memory.event.lower()
        if (
            current_goal is None
            and not self._is_informative_event(event)
        ):
            return None

        observation = memory.event.strip()

        interpretation = self._interpret(
            memory,
            current_goal,
        )

        lesson = self._lesson(
            memory,
            current_goal,
        )

        suggested_behavior = self._suggested_behavior(
            memory,
            current_goal,
        )

        return ExperienceReflection(
            memory=memory,
            observation=observation,
            interpretation=interpretation,
            lesson=lesson,
            suggested_behavior=suggested_behavior,
        )

    def _is_informative_event(self, event: str) -> bool:
        informative_markers = (
            "helped",
            "gave",
            "refused",
            "rejected",
            "failed",
            "borrowed",
            "lent",
            "money",
            "credit",
            "food",
            "bought",
            "sold",
            "stole",
            "asked",
            "apologized",
            "argued",
            "fought",
            "ignored",
            "supported",
            "disagreed",
            "demanded",
        )

        return any(marker in event for marker in informative_markers)

    def _interpret(
        self,
        memory: Memory,
        current_goal: str | None,
    ) -> str:
        event = memory.event.lower()

        if "refused" in event or "rejected" in event:
            return (
                "The experience indicates that the expected "
                "outcome was not available from this interaction."
            )

        if "helped" in event or "gave" in event:
            return (
                "The experience indicates that another person "
                "provided useful support."
            )

        if "failed" in event:
            return (
                "The experience indicates that the attempted "
                "approach did not produce the expected result."
            )

        if current_goal:
            return (
                f"The experience occurred while pursuing "
                f"{current_goal}."
            )

        return (
            "The experience provides information about the "
            "current environment and circumstances."
        )

    def _lesson(
        self,
        memory: Memory,
        current_goal: str | None,
    ) -> str:
        event = memory.event.lower()

        if "refused" in event or "rejected" in event:
            return (
                "Do not rely on the same interaction producing "
                "the desired outcome."
            )

        if "helped" in event or "gave" in event:
            return (
                "This interaction may be useful when similar "
                "support is needed in the future."
            )

        if "failed" in event:
            return (
                "The previous approach may need to be changed "
                "when the same conditions occur again."
            )

        if current_goal:
            return (
                "Remember this experience when pursuing the "
                "same goal again."
            )

        return (
            "Remember the circumstances surrounding this event."
        )

    def _suggested_behavior(
        self,
        memory: Memory,
        current_goal: str | None,
    ) -> str:
        event = memory.event.lower()

        if "refused" in event or "rejected" in event:
            return (
                "Consider an alternative person or approach."
            )

        if "helped" in event or "gave" in event:
            return (
                "Consider this interaction when choosing "
                "whom to approach for help."
            )

        if "failed" in event:
            return (
                "Try a different approach under similar "
                "conditions."
            )

        if current_goal:
            return (
                "Use this experience when planning the next "
                "step toward the goal."
            )

        return (
            "Use this experience when evaluating similar events."
        )