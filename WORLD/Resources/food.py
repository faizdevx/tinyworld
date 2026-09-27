from dataclasses import dataclass


@dataclass
class Resource:
    name: str
    quantity: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Resource name cannot be empty.")

        if self.quantity < 0:
            raise ValueError("Resource quantity cannot be negative.")

    def add(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        self.quantity += amount

    def consume(self, amount: int) -> bool:
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        if self.quantity < amount:
            return False

        self.quantity -= amount
        return True