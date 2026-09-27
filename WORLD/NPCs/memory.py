from dataclasses import dataclass


@dataclass
class Memory:
    day: int
    hour: int
    event: str
    importance: int

    def __post_init__(self) -> None:
        if self.day < 1:
            raise ValueError("Day must be at least 1.")

        if not 0 <= self.hour <= 23:
            raise ValueError("Hour must be between 0 and 23.")

        if not self.event.strip():
            raise ValueError("Memory event cannot be empty.")

        if self.importance < 0:
            raise ValueError("Memory importance cannot be negative.")