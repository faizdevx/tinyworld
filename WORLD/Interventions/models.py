from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class InterventionOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    REMOVE = "remove"
    MOVE = "move"
    SPAWN = "spawn"
    DESPAWN = "despawn"
    TRIGGER_EVENT = "trigger_event"
    CHANGE_ENVIRONMENT = "change_environment"
    CHANGE_RESOURCE = "change_resource"
    CHANGE_RULE = "change_rule"
    ADVANCE_TIME = "advance_time"


class InterventionVisibility(str, Enum):
    GOD_ONLY = "god_only"
    WORLD = "world"


@dataclass(frozen=True)
class GodIntervention:
    operation: InterventionOperation | str
    target: str
    properties: Mapping[str, Any] = field(default_factory=dict)
    value: Any = None
    visibility: InterventionVisibility | str = (
        InterventionVisibility.GOD_ONLY
    )

    def __post_init__(self) -> None:
        if isinstance(self.operation, str):
            normalized = self.operation.strip().lower().replace("-", "_")
            try:
                operation = InterventionOperation(normalized)
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported intervention operation: {self.operation}"
                ) from exc
            object.__setattr__(self, "operation", operation)

        if not isinstance(self.operation, InterventionOperation):
            raise TypeError("operation must be an InterventionOperation")

        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("target cannot be empty")

        if not isinstance(self.properties, Mapping):
            raise TypeError("properties must be a mapping")

        object.__setattr__(
            self,
            "properties",
            MappingProxyType(dict(self.properties)),
        )

        if isinstance(self.visibility, str):
            normalized = self.visibility.strip().lower().replace("-", "_")
            try:
                visibility = InterventionVisibility(normalized)
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported intervention visibility: {self.visibility}"
                ) from exc
            object.__setattr__(self, "visibility", visibility)

        if not isinstance(self.visibility, InterventionVisibility):
            raise TypeError(
                "visibility must be an InterventionVisibility"
            )

        if self.operation == InterventionOperation.ADVANCE_TIME:
            if not isinstance(self.value, int) or isinstance(self.value, bool):
                raise TypeError("ADVANCE_TIME value must be an integer")
            if self.value < 0:
                raise ValueError("ADVANCE_TIME value cannot be negative")

        if self.operation == InterventionOperation.CHANGE_RESOURCE:
            if not isinstance(self.value, int) or isinstance(self.value, bool):
                raise TypeError("CHANGE_RESOURCE value must be an integer")


@dataclass(frozen=True)
class InterventionResult:
    success: bool
    operation: InterventionOperation
    target: str
    message: str
    changed: bool


@dataclass(frozen=True)
class InterventionAudit:
    intervention: GodIntervention
    result: InterventionResult
    day: int
    hour: int
    before: Any = None
    after: Any = None
