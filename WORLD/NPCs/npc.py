from dataclasses import dataclass, field
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
    schedule: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.money < 0:
            raise ValueError("Money cannot be negative.")

        if self.food < 0:
            raise ValueError("Food cannot be negative.")

        if not 0 <= self.energy <= 100:
            raise ValueError("Energy must be between 0 and 100.")

        for hour, location in self.schedule.items():
            if not 0 <= hour <= 23:
                raise ValueError("Schedule hour must be between 0 and 23.")

            if not location:
                raise ValueError("Schedule location cannot be empty.")

    def move_to(
        self,
        location: str,
        position: Optional[Position] = None
    ) -> None:
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

    def eat(
        self,
        food_amount: int = 1,
        energy_gain: int = 20
    ) -> bool:
        if energy_gain < 0:
            raise ValueError("Energy gain cannot be negative.")

        if not self.consume_food(food_amount):
            return False

        self.restore_energy(energy_gain)
        return True