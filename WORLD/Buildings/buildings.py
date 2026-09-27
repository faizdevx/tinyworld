from dataclasses import dataclass


@dataclass
class Building:
    name: str
    building_type: str
    money: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Building name cannot be empty.")

        if not self.building_type:
            raise ValueError("Building type cannot be empty.")

        if self.money < 0:
            raise ValueError("Building money cannot be negative.")

    def add_money(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Money amount cannot be negative.")

        self.money += amount