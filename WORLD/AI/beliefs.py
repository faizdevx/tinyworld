from dataclasses import dataclass


@dataclass
class Belief:
    subject: str
    predicate: str
    value: object
    confidence: float
    source: str | None = None
    origin_type: str | None = None

    def __post_init__(self):
        if not self.subject:
            raise ValueError("subject cannot be empty")

        if not self.predicate:
            raise ValueError("predicate cannot be empty")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        if self.source is not None and not self.source.strip():
            raise ValueError("source cannot be empty")

        if self.origin_type is not None and not self.origin_type.strip():
            raise ValueError("origin_type cannot be empty")