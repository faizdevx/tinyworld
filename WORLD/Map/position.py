from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def manhattan_distance_to(self, other: "Position") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def move(self, dx: int, dy: int) -> "Position":
        return Position(
            x=self.x + dx,
            y=self.y + dy
        )

    def is_adjacent_to(self, other: "Position") -> bool:
        return self.manhattan_distance_to(other) == 1