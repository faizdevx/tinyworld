from dataclasses import dataclass, field
from typing import Mapping


@dataclass
class WorldEntity:
    name: str
    entity_type: str
    location: str | None = None
    properties: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Entity name cannot be empty.")

        if not self.entity_type.strip():
            raise ValueError("Entity type cannot be empty.")

        if self.location is not None and not self.location.strip():
            raise ValueError("Entity location cannot be empty.")

        if not isinstance(self.properties, Mapping):
            raise TypeError("Entity properties must be a mapping.")

        self.properties = dict(self.properties)
