from dataclasses import dataclass


@dataclass
class Personality:
    """
    Numeric behavioral tendencies for an NPC.

    All values use the normalized range [0.0, 1.0].
    """

    risk_tolerance: float = 0.5
    sociability: float = 0.5
    generosity: float = 0.5
    ambition: float = 0.5
    patience: float = 0.5

    def __post_init__(self) -> None:
        values = {
            "risk_tolerance": self.risk_tolerance,
            "sociability": self.sociability,
            "generosity": self.generosity,
            "ambition": self.ambition,
            "patience": self.patience,
        }

        for name, value in values.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{name} must be between 0.0 and 1.0."
                )
