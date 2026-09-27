from dataclasses import dataclass
from typing import Optional

from WORLD.Map.position import Position


@dataclass
class NPC:
    name: str
    role: str
    money: int
    home: str
    location: str
    food: int = 0
    energy: int = 100
    position: Optional[Position] = None

    def __post_init__(self) -> None:
        if self.money < 0:
            raise ValueError("Money cannot be negative.")

        if self.food < 0:
            raise ValueError("Food cannot be negative.")

        if not 0 <= self.energy <= 100:
            raise ValueError("Energy must be between 0 and 100.")

    def move_to(self, location: str, position: Optional[Position] = None) -> None:
        """Move the NPC instantly to a new location.

        Phase 1 deliberately uses teleportation instead of pathfinding.
        """
        if not location:
            raise ValueError("Location cannot be empty.")

        self.location = location
        self.position = position

    def add_food(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Food amount cannot be negative.")

        self.food += amount

    def consume_food(self, amount: int = 1) -> bool:
        if amount <= 0:
            raise ValueError("Food amount must be positive.")

        if self.food < amount:
            return False

        self.food -= amount
        return True

    def restore_energy(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Energy amount cannot be negative.")

        self.energy = min(100, self.energy + amount)

    def use_energy(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Energy amount cannot be negative.")

        self.energy = max(0, self.energy - amount)

    def eat(self, food_amount: int = 1, energy_gain: int = 20) -> bool:
        """Consume food and restore energy."""
        if energy_gain < 0:
            raise ValueError("Energy gain cannot be negative.")

        if not self.consume_food(food_amount):
            return False

        self.restore_energy(energy_gain)
        return True