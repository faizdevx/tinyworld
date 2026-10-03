from WORLD.AI.beliefs import Belief
from WORLD.AI.observation import ObservationSystem


class Perception:
    """
    Provides an NPC with observations of the current world state.

    Phase 6.10 uses perfect perception:
    observations reflect reality directly.
    """

    def __init__(self, observation_system=None):
        self.observation_system = (
            observation_system
            if observation_system is not None
            else ObservationSystem()
        )
        self.last_observations = []

    def observe_world(self, npc, world):
        self.last_observations = self.observation_system.observe(
            world,
            npc,
        )
        return list(self.last_observations)

    def observe(self, npc, world) -> list[Belief]:
        self.observe_world(npc, world)
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

        beliefs.extend(
            Belief(
                subject=observation.subject,
                predicate="observation",
                value=observation.description,
                confidence=observation.confidence,
            )
            for observation in self.last_observations
        )

        return beliefs