from dataclasses import dataclass


@dataclass
class Belief:
    subject: str
    predicate: str
    value: object
    confidence: float

    def __post_init__(self):
        if not self.subject:
            raise ValueError("subject cannot be empty")

        if not self.predicate:
            raise ValueError("predicate cannot be empty")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")