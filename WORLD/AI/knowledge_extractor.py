from WORLD.AI.experience_reflection import ExperienceReflection
from WORLD.AI.knowledge import Knowledge


class KnowledgeExtractor:
    """
    Converts structured experience reflections into generalized
    knowledge when the experience contains enough information.
    """

    def extract(self, npc, reflection: ExperienceReflection) -> Knowledge | None:
        if reflection is None:
            return None

        memory = reflection.memory
        if memory is None:
            return None

        event = memory.event.lower()
        subject = self._counterpart(npc, memory.participants)
        if subject is None:
            return None

        if ("refused" in event or "rejected" in event) and (
            "money" in event or "credit" in event
        ):
            return Knowledge(
                subject=subject,
                predicate="provides_financial_credit",
                value=False,
                confidence=0.9,
            )

        if "helped" in event or "gave" in event:
            return Knowledge(
                subject=subject,
                predicate="provides_help",
                value=True,
                confidence=0.9,
            )

        return None

    def _counterpart(self, npc, participants):
        if npc is None:
            return None

        npc_name = getattr(npc, "name", None)
        if not npc_name:
            return None

        if not participants:
            return None

        for participant in participants:
            if participant and participant != npc_name:
                return participant

        return None
