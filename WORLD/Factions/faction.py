from dataclasses import dataclass


@dataclass
class Faction:
    name: str
    faction_type: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Faction name cannot be empty.")

        if not self.faction_type.strip():
            raise ValueError("Faction type cannot be empty.")
