from dataclasses import dataclass, field

from WORLD.NPCs.memory import Memory


@dataclass
class SocialMemoryStore:
    """
    Per-NPC history of experiences involving other NPCs.

    Memories remain the authoritative episodic evidence. This store
    indexes them by participant for efficient social retrieval.
    """

    _memories_by_person: dict[str, list[Memory]] = field(
        default_factory=dict
    )

    def record(self, npc, memory: Memory) -> None:
        if memory is None:
            raise ValueError("Memory cannot be None.")

        npc_name = getattr(npc, "name", None)
        for participant in memory.participants:
            if participant == npc_name:
                continue
            self._memories_by_person.setdefault(participant, []).append(
                memory
            )

    def for_person(
        self,
        person: str,
        *,
        limit: int | None = None,
    ) -> list[Memory]:
        if person is None or not person.strip():
            return []
        if limit is not None and limit <= 0:
            raise ValueError("Social memory limit must be positive.")

        memories = list(self._memories_by_person.get(person, []))
        ordered = list(reversed(memories))

        if limit is None:
            return ordered

        return ordered[:limit]

    def count(self, person: str) -> int:
        return len(self._memories_by_person.get(person, []))

    def people(self) -> list[str]:
        return list(self._memories_by_person.keys())
