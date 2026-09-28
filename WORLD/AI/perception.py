from WORLD.AI.beliefs import Belief


class Perception:
    """
    Provides an NPC with observations of the current world state.

    Phase 6.10 uses perfect perception:
    observations reflect reality directly.
    """

    def observe(self, npc, world) -> list[Belief]:
        beliefs = [
            Belief(
                subject=npc.name,
                predicate="hunger",
                value=npc.hunger,
                confidence=1.0,
            ),
            Belief(
                subject=npc.name,
                predicate="energy",
                value=npc.energy,
                confidence=1.0,
            ),
            Belief(
                subject=npc.name,
                predicate="money",
                value=npc.money,
                confidence=1.0,
            ),
            Belief(
                subject=npc.name,
                predicate="location",
                value=npc.location,
                confidence=1.0,
            ),
        ]

        return beliefs