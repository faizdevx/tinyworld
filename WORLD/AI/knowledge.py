from dataclasses import dataclass


@dataclass(frozen=True)
class Knowledge:
    """
    Generalized information derived from one or more experiences.
    """

    subject: str
    predicate: str
    value: object
    confidence: float
    evidence_count: int = 1

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("Knowledge subject cannot be empty.")
        if not self.predicate.strip():
            raise ValueError("Knowledge predicate cannot be empty.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Knowledge confidence must be between 0.0 and 1.0."
            )
        if self.evidence_count < 1:
            raise ValueError(
                "Knowledge evidence_count must be at least 1."
            )


class KnowledgeBase:
    """
    Persistent generalized knowledge for an NPC.

    Repeated evidence for the same fact merges into one record,
    rather than creating a duplicate event log entry.
    """

    def __init__(self):
        self.entries: list[Knowledge] = []

    def add(
        self,
        *,
        subject: str,
        predicate: str,
        value: object,
        confidence: float,
    ) -> Knowledge:
        candidate = Knowledge(
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
        )

        for index, existing in enumerate(self.entries):
            if (
                existing.subject == candidate.subject
                and existing.predicate == candidate.predicate
                and existing.value == candidate.value
            ):
                merged_confidence = (
                    existing.confidence * existing.evidence_count
                    + candidate.confidence
                ) / (existing.evidence_count + 1)
                merged = Knowledge(
                    subject=existing.subject,
                    predicate=existing.predicate,
                    value=existing.value,
                    confidence=merged_confidence,
                    evidence_count=existing.evidence_count + 1,
                )
                self.entries[index] = merged
                return merged

        self.entries.append(candidate)
        return candidate

    def for_subject(self, subject: str) -> list[Knowledge]:
        if not subject or not subject.strip():
            return []
        return [
            entry
            for entry in self.entries
            if entry.subject == subject
        ]

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __bool__(self) -> bool:
        return bool(self.entries)
