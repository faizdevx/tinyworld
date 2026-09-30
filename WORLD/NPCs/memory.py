from dataclasses import dataclass, field


@dataclass
class Memory:
    """
    Structured episodic memory for an NPC.

    day and hour remain the authoritative simulation time fields.
    timestamp is an absolute hour index derived from them unless
    explicitly supplied.

    importance remains nonnegative for Phase 8.1 so existing
    memory records remain backward compatible. Normalized
    importance belongs to Phase 8.2.
    """

    day: int
    hour: int
    event: str
    importance: float
    memory_type: str = "event"
    timestamp: int | None = None
    location: str | None = None
    participants: list[str] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        if self.day < 1:
            raise ValueError("Day must be at least 1.")

        if not 0 <= self.hour <= 23:
            raise ValueError("Hour must be between 0 and 23.")

        if not self.event.strip():
            raise ValueError("Memory event cannot be empty.")

        if self.importance < 0:
            raise ValueError("Memory importance cannot be negative.")

        if not self.memory_type.strip():
            raise ValueError("Memory type cannot be empty.")

        if self.timestamp is None:
            self.timestamp = (
                (self.day - 1) * 24
                + self.hour
            )
        elif self.timestamp < 0:
            raise ValueError(
                "Memory timestamp cannot be negative."
            )

        if self.location is not None:
            if not self.location.strip():
                raise ValueError(
                    "Memory location cannot be empty."
                )

        for participant in self.participants:
            if not isinstance(participant, str):
                raise ValueError(
                    "Memory participants must be strings."
                )

            if not participant.strip():
                raise ValueError(
                    "Memory participant names cannot be empty."
                )