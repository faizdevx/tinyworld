from dataclasses import dataclass, field


@dataclass
class WorldScenario:
    """
    Declarative definition of a world before generation.

    This class describes what the world should contain, without
    constructing concrete simulation entities.
    """

    era: str = "15th century"
    geography: str = "small settlement"
    climate: str = "temperate"
    population: int = 10
    resources: dict[str, int] = field(default_factory=dict)
    buildings: list[str] = field(default_factory=list)
    factions: list[str] = field(default_factory=list)
    landmarks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.era.strip():
            raise ValueError("era cannot be empty")
        if not self.geography.strip():
            raise ValueError("geography cannot be empty")
        if not self.climate.strip():
            raise ValueError("climate cannot be empty")
        if self.population < 0:
            raise ValueError("population must be non-negative")
        if not isinstance(self.resources, dict):
            raise ValueError("resources must be a dictionary")
        if not isinstance(self.buildings, list):
            raise ValueError("buildings must be a list")
        if not isinstance(self.factions, list):
            raise ValueError("factions must be a list")
        if not isinstance(self.landmarks, list):
            raise ValueError("landmarks must be a list")
        for key, value in self.resources.items():
            if not key.strip():
                raise ValueError("resource names cannot be empty")
            if value < 0:
                raise ValueError("resource quantities cannot be negative")
        for building in self.buildings:
            if not building.strip():
                raise ValueError("building names cannot be empty")
        for faction in self.factions:
            if not faction.strip():
                raise ValueError("faction names cannot be empty")
        for landmark in self.landmarks:
            if not landmark.strip():
                raise ValueError("landmark names cannot be empty")
