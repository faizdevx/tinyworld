from dataclasses import dataclass, field
from typing import ClassVar, Optional

from WORLD.Map.position import Position
from WORLD.NPCs.memory import Memory
from WORLD.NPCs.relationship import Relationship


@dataclass
class NPC:
    name: str
    role: str
    money: int
    home: str
    location: str
    food: int = 0
    energy: int = 100
    hunger: int = 0
    position: Optional[Position] = None
    schedule: dict[int, str] = field(default_factory=dict)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    memories: list[Memory] = field(default_factory=list)
    reputation:int=0
    MAX_MEMORIES: ClassVar[int] = 50

    def __post_init__(self) -> None:
        if self.money < 0:
            raise ValueError("Money cannot be negative.")

        if self.food < 0:
            raise ValueError("Food cannot be negative.")

        if not 0 <= self.energy <= 100:
            raise ValueError("Energy must be between 0 and 100.")

        if not 0 <= self.hunger <= 100:
            raise ValueError("Hunger must be between 0 and 100.")

        if not -100<=self.reputation<=100:
            raise ValueError(
                "Reputation must be between -100 and 100"
            )
            
        for hour, location in self.schedule.items():
            if not 0 <= hour <= 23:
                raise ValueError(
                    f"Invalid schedule hour: {hour}. "
                    "Hour must be between 0 and 23."
                )

            if not location:
                raise ValueError("Schedule location cannot be empty.")

    def move_to(
        self,
        location: str,
        position: Optional[Position] = None,
    ) -> None:
        if not location:
            raise ValueError("Location cannot be empty.")

        self.location = location
        self.position = position

    # -------------------------
    # Food
    # -------------------------

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

    # -------------------------
    # Hunger
    # -------------------------

    def increase_hunger(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Hunger increase cannot be negative.")

        self.hunger = min(100, self.hunger + amount)

    def decrease_hunger(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Hunger decrease cannot be negative.")

        self.hunger = max(0, self.hunger - amount)

    # -------------------------
    # Energy
    # -------------------------

    def restore_energy(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Energy amount cannot be negative.")

        self.energy = min(100, self.energy + amount)

    def use_energy(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Energy amount cannot be negative.")

        self.energy = max(0, self.energy - amount)

    # -------------------------
    # Eating
    # -------------------------

    def eat(
        self,
        food_amount: int = 1,
        hunger_reduction: int = 40,
        energy_gain: int = 20,
    ) -> bool:
        if hunger_reduction < 0:
            raise ValueError(
                "Hunger reduction cannot be negative."
            )

        if energy_gain < 0:
            raise ValueError(
                "Energy gain cannot be negative."
            )

        if not self.consume_food(food_amount):
            return False

        self.decrease_hunger(hunger_reduction)
        self.restore_energy(energy_gain)

        return True

    # -------------------------
    # Productivity
    # -------------------------

    @property
    def productivity(self) -> float:
        if self.energy < 30:
            return 0.5

        return 1.0

    # -------------------------
    # Relationships
    # -------------------------

    def get_relationship(self, other: "NPC") -> int:
        relationship = self.relationships.get(other.name)

        if relationship is None:
            return 0

        return relationship.value

    def change_relationship(
        self,
        other: "NPC",
        amount: int,
    ) -> None:
        if other.name == self.name:
            raise ValueError(
                "An NPC cannot have a relationship with itself."
            )

        relationship = self.relationships.get(other.name)

        if relationship is None:
            relationship = Relationship(
                npc_a=self,
                npc_b=other,
            )
            self.relationships[other.name] = relationship

        if amount >= 0:
            relationship.improve(amount)
        else:
            relationship.worsen(-amount)

    # -------------------------
    # Memories
    # -------------------------

    def remember(self, memory: Memory) -> None:
        self.memories.append(memory)

        if len(self.memories) > self.MAX_MEMORIES:
            self.memories.pop(0)