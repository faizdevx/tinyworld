from dataclasses import dataclass


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