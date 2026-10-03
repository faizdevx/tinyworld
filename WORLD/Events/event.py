from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


class EventSource(str, Enum):
    NPC = "npc"
    GOD = "god"
    SYSTEM = "system"


@dataclass(frozen=True)
class EventProposal:
    actor: str
    action_type: object
    target: str | None = None
    properties: Mapping[str, object] = field(default_factory=dict)
    source: EventSource | str = EventSource.NPC
    timestamp: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise ValueError("Proposal actor cannot be empty.")
        if self.target is not None and not self.target.strip():
            raise ValueError("Proposal target cannot be empty.")
        if not isinstance(self.properties, Mapping):
            raise TypeError("Proposal properties must be a mapping.")
        object.__setattr__(
            self,
            "properties",
            _freeze(self.properties),
        )
        if isinstance(self.source, str):
            try:
                object.__setattr__(self, "source", EventSource(self.source.lower()))
            except ValueError as exc:
                raise ValueError("Unsupported event proposal source.") from exc
        if not isinstance(self.source, EventSource):
            raise TypeError("source must be an EventSource")


@dataclass(frozen=True)
class EventValidationResult:
    success: bool
    reason: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "details",
            _freeze(self.details),
        )


@dataclass(frozen=True)
class Consequence:
    kind: str
    target: str
    properties: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "properties",
            _freeze(self.properties),
        )


@dataclass(frozen=True)
class WorldEvent:
    """
    Represents something meaningful that happened in the world.
    """

    day: int
    hour: int
    event_type: str
    actor: str
    target: str | None
    description: str
    properties: Mapping[str, object] = field(default_factory=dict)
    consequences: tuple[Consequence, ...] = ()
    sequence: int = field(default=0, compare=False)
    cause: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "properties",
            _freeze(self.properties),
        )
        object.__setattr__(self, "consequences", tuple(self.consequences))


@dataclass(frozen=True)
class EventResolution:
    event: WorldEvent
    consequences: tuple[Consequence, ...]


@dataclass(frozen=True)
class EventProcessingResult:
    success: bool
    validation: EventValidationResult
    resolution: EventResolution | None = None
    reason: str = ""
    before: object = None
    after: object = None

    @property
    def event(self) -> WorldEvent | None:
        return self.resolution.event if self.resolution else None

    @property
    def consequences(self) -> tuple[Consequence, ...]:
        return self.resolution.consequences if self.resolution else ()