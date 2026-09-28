import random


class SimulationRNG:
    def __init__(self, seed: int):
        self.seed = seed
        self.random = random.Random(seed)

    def random_float(self) -> float:
        return self.random.random()

    def randint(self, minimum: int, maximum: int) -> int:
        return self.random.randint(minimum, maximum)

    def choice(self, values):
        if not values:
            raise ValueError("values cannot be empty")

        return self.random.choice(values)