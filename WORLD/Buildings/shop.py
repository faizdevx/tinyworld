from dataclasses import dataclass


@dataclass
class Shop:
    name: str
    money: int
    food: int
    food_price: int = 5

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Shop name cannot be empty.")

        if self.money < 0:
            raise ValueError("Money cannot be negative.")

        if self.food < 0:
            raise ValueError("Food cannot be negative.")

        if self.food_price <= 0:
            raise ValueError("Food price must be positive.")