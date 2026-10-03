from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ObservationType(str, Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    SOCIAL = "social"
    PUBLIC = "public"


@dataclass(frozen=True)
class Observation:
    observer: str
    subject: str
    description: str
    location: str | None
    distance: int | None
    source: str
    observation_type: ObservationType
    timestamp: tuple[int, int]
    confidence: float = 1.0
    facts: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.observer.strip():
            raise ValueError("Observation observer cannot be empty.")
        if not self.subject.strip():
            raise ValueError("Observation subject cannot be empty.")
        if not self.description.strip():
            raise ValueError("Observation description cannot be empty.")
        if not self.source.strip():
            raise ValueError("Observation source cannot be empty.")
        if not isinstance(self.observation_type, ObservationType):
            raise TypeError(
                "observation_type must be an ObservationType"
            )
        if self.distance is not None and self.distance < 0:
            raise ValueError("Observation distance cannot be negative.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Observation confidence must be between 0.0 and 1.0."
            )
        if not isinstance(self.facts, Mapping):
            raise TypeError("Observation facts must be a mapping.")
        object.__setattr__(
            self,
            "facts",
            MappingProxyType(dict(self.facts)),
        )


@dataclass(frozen=True)
class CognitionClockView:
    day: int
    hour: int


@dataclass(frozen=True)
class CognitionShopView:
    name: str
    food: int
    food_price: int


@dataclass(frozen=True)
class CognitionNPCView:
    name: str
    location: str | None


@dataclass(frozen=True)
class CognitionWorldView:
    clock: CognitionClockView
    shop: CognitionShopView
    npcs: tuple[CognitionNPCView, ...]


class ObservationSystem:
    """Convert world truth into deterministic, NPC-specific snapshots."""

    DEFAULT_VISION_RANGE = 0
    DEFAULT_HEARING_RANGE = 1
    DEFAULT_ATTENTION_LIMIT = 5

    LOCATION_DISTANCES = {
        frozenset(("Forest", "Road")): 1,
        frozenset(("Forest", "Settlement")): 2,
        frozenset(("Road", "Settlement")): 1,
        frozenset(("River", "Settlement")): 1,
        frozenset(("River", "Road")): 1,
        frozenset(("Coast", "River")): 1,
        frozenset(("Coast", "Settlement")): 2,
    }

    def __init__(
        self,
        *,
        vision_range: int = DEFAULT_VISION_RANGE,
        hearing_range: int = DEFAULT_HEARING_RANGE,
        attention_limit: int = DEFAULT_ATTENTION_LIMIT,
    ) -> None:
        if vision_range < 0:
            raise ValueError("vision_range cannot be negative")
        if hearing_range < 0:
            raise ValueError("hearing_range cannot be negative")
        if attention_limit < 0:
            raise ValueError("attention_limit cannot be negative")
        self.vision_range = vision_range
        self.hearing_range = hearing_range
        self.attention_limit = attention_limit

    def observe(self, world, npc) -> list[Observation]:
        candidates = []
        for entity in getattr(world, "entities", []):
            observation = self._observe_entity(world, npc, entity)
            if observation is not None:
                candidates.append(observation)

        for event in getattr(getattr(world, "event_log", None), "events", []):
            observation = self._observe_event(world, npc, event)
            if observation is not None:
                candidates.append(observation)

        candidates.sort(key=self._priority)
        return candidates[: self.attention_limit]

    def cognition_view(self, world, npc) -> CognitionWorldView:
        nearby_npcs = tuple(
            CognitionNPCView(
                name=other.name,
                location=getattr(other, "location", None),
            )
            for other in getattr(world, "npcs", [])
            if other is not npc
            and getattr(other, "location", None) == npc.location
        )
        return CognitionWorldView(
            clock=CognitionClockView(
                day=world.clock.day,
                hour=world.clock.hour,
            ),
            shop=CognitionShopView(
                name=world.shop.name,
                food=world.shop.food,
                food_price=world.shop.food_price,
            ),
            npcs=nearby_npcs,
        )

    def visible(self, world, observer, target) -> bool:
        distance = self.distance(observer.location, target.location)
        return distance is not None and distance <= self.vision_range

    def can_see(self, world, observer, target) -> bool:
        return self.visible(world, observer, target)

    def hear(self, world, observer, target) -> bool:
        distance = self.distance(observer.location, target.location)
        return distance is not None and distance <= self.hearing_range

    @classmethod
    def distance(
        cls,
        first_location: str | None,
        second_location: str | None,
    ) -> int | None:
        if not first_location or not second_location:
            return None
        if first_location == second_location:
            return 0
        return cls.LOCATION_DISTANCES.get(
            frozenset((first_location, second_location))
        )

    def _observe_entity(self, world, npc, entity) -> Observation | None:
        entity_location = getattr(entity, "location", None)
        distance = self.distance(npc.location, entity_location)
        if distance is None:
            return None

        if distance <= self.vision_range:
            observation_type = ObservationType.VISUAL
            description = self._visual_description(entity)
        elif distance <= self.hearing_range:
            observation_type = ObservationType.AUDITORY
            description = f"Movement associated with {entity.name} was heard."
        else:
            return None

        facts = {
            "entity_type": entity.entity_type,
        }
        size = getattr(entity, "properties", {}).get("size")
        if isinstance(size, int):
            facts["perceived_size"] = self._perceived_size(size)

        return Observation(
            observer=npc.name,
            subject=entity.name,
            description=description,
            location=entity_location,
            distance=distance,
            source="world_entity",
            observation_type=observation_type,
            timestamp=(world.clock.day, world.clock.hour),
            facts=facts,
        )

    def _observe_event(self, world, npc, event) -> Observation | None:
        event_location = event.target
        distance = self.distance(npc.location, event_location)
        if distance is None:
            return None
        if distance > self.hearing_range:
            return None
        return Observation(
            observer=npc.name,
            subject=event.event_type,
            description=event.description,
            location=event_location,
            distance=distance,
            source="world_event",
            observation_type=ObservationType.AUDITORY,
            timestamp=(event.day, event.hour),
            facts={"actor": event.actor},
        )

    @staticmethod
    def _visual_description(entity) -> str:
        if entity.entity_type == "army":
            return "A large group of organized movement was seen."
        return f"{entity.name} was seen nearby."

    @staticmethod
    def _perceived_size(size: int) -> str:
        if size >= 100:
            return "large"
        if size >= 20:
            return "medium"
        return "small"

    @staticmethod
    def _priority(observation: Observation):
        type_priority = {
            ObservationType.VISUAL: 0,
            ObservationType.AUDITORY: 1,
            ObservationType.SOCIAL: 2,
            ObservationType.PUBLIC: 3,
        }
        return (
            observation.distance
            if observation.distance is not None
            else 10**9,
            type_priority[observation.observation_type],
            observation.subject,
            observation.description,
        )