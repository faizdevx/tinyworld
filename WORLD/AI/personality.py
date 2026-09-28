from dataclasses import dataclass


@dataclass
class Personality:
    risk_tolerance: float
    sociability: float
    generosity: float
    ambition: float
    patience: float