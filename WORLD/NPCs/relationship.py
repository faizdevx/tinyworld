from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from WORLD.NPCs.npc import NPC


@dataclass
class Relationship:
    npc_a: "NPC"
    npc_b: "NPC"
    value: int = 0

    MIN_VALUE = -100
    MAX_VALUE = 100

    def __post_init__(self) -> None:
        if not isinstance(self.value, int):
            raise TypeError("Relationship value must be an integer.")

        self.value = max(
            self.MIN_VALUE,
            min(self.value, self.MAX_VALUE),
        )

    def improve(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Improvement amount must be non-negative.")

        self.value = min(
            self.value + amount,
            self.MAX_VALUE,
        )

    def worsen(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Worsening amount must be non-negative.")

        self.value = max(
            self.value - amount,
            self.MIN_VALUE,
        )