from dataclasses import dataclass
import re

from WORLD.NPCs.memory import Memory


@dataclass(frozen=True)
class RetrievalContext:
    """
    Context used when ranking memories.

    current_timestamp is expressed in the same absolute-hour
    coordinate used by Memory.timestamp.
    """

    current_timestamp: int | None = None
    query: str = ""
    current_goal: str | None = None


@dataclass(frozen=True)
class MemoryRetrievalResult:
    memory: Memory
    score: float


class MemoryRetriever:
    """
    Deterministic memory retrieval interface.

    The current backend uses lexical matching rather than
    semantic embeddings. The public retrieve() API is designed
    so the ranking strategy can be replaced later.
    """

    def relevant_memories(
        self,
        npc,
        topic: str,
    ) -> list[Memory]:
        """
        Backward-compatible Phase 6 retrieval API.
        """
        return self.retrieve(
            npc,
            topic,
            limit=None,
            min_importance=0.0,
        )

    def retrieve(
        self,
        npc,
        query: str,
        *,
        limit: int | None = 5,
        min_importance: float = 0.0,
        current_timestamp: int | None = None,
    ) -> list[Memory]:
        if not query:
            return []

        if limit is not None and limit < 1:
            raise ValueError(
                "limit must be at least 1."
            )

        if not 0.0 <= min_importance:
            raise ValueError(
                "min_importance cannot be negative."
            )

        current_goal = self._current_goal_text(npc)

        context = RetrievalContext(
            current_timestamp=current_timestamp,
            query=query,
            current_goal=current_goal,
        )

        candidates = [
            memory
            for memory in getattr(
                npc,
                "memories",
                [],
            )
            if memory.importance >= min_importance
        ]

        ranked = [
            MemoryRetrievalResult(
                memory=memory,
                score=self._score(
                    npc,
                    memory,
                    context,
                ),
            )
            for memory in candidates
        ]

        ranked = [
            result
            for result in ranked
            if result.score > 0.0
        ]

        ranked.sort(
            key=lambda result: (
                result.score,
                result.memory.timestamp,
            ),
            reverse=True,
        )

        return [
            result.memory
            for result in ranked[:limit]
        ]

    def _score(
        self,
        npc,
        memory: Memory,
        context: RetrievalContext,
    ) -> float:
        lexical = self._lexical_relevance(
            memory,
            context.query,
        )

        if lexical == 0.0:
            return 0.0

        importance = self._importance_score(
            memory,
        )

        recency = self._recency_score(
            memory,
            context.current_timestamp,
        )

        relationship = self._relationship_relevance(
            npc,
            memory,
            context.query,
        )

        goal = self._goal_relevance(
            memory,
            context.current_goal,
        )

        return (
            lexical * 0.50
            + importance * 0.20
            + recency * 0.15
            + relationship * 0.10
            + goal * 0.05
        )

    def _lexical_relevance(
        self,
        memory: Memory,
        query: str,
    ) -> float:
        query_terms = self._terms(query)

        if not query_terms:
            return 0.0

        text = " ".join(
            [
                memory.event,
                memory.memory_type,
                memory.location or "",
                *memory.participants,
            ]
        ).lower()

        matched = sum(
            term in text
            for term in query_terms
        )

        return matched / len(query_terms)

    def _importance_score(
        self,
        memory: Memory,
    ) -> float:
        """
        Treat legacy importance values as a relative signal.

        Phase 8.2 introduces normalized importance separately.
        Legacy memories remain compatible here.
        """
        if memory.importance <= 0:
            return 0.0

        return min(
            float(memory.importance) / 10.0,
            1.0,
        )

    def _recency_score(
        self,
        memory: Memory,
        current_timestamp: int | None,
    ) -> float:
        if current_timestamp is None:
            return 0.0

        age = max(
            0,
            current_timestamp - memory.timestamp,
        )

        return 1.0 / (1.0 + age)

    def _relationship_relevance(
        self,
        npc,
        memory: Memory,
        query: str,
    ) -> float:
        participant_names = {
            participant.lower()
            for participant in memory.participants
        }

        relationship_names = {
            name.lower()
            for name in getattr(
                npc,
                "relationships",
                {},
            )
        }

        if not participant_names:
            return 0.0

        query_terms = self._terms(query)

        relevant_participants = (
            participant_names
            & relationship_names
        )

        if not relevant_participants:
            return 0.0

        if any(
            term in participant
            for term in query_terms
            for participant in relevant_participants
        ):
            return 1.0

        return 0.5

    def _goal_relevance(
        self,
        memory: Memory,
        current_goal: str | None,
    ) -> float:
        if not current_goal:
            return 0.0

        goal_terms = self._terms(
            current_goal,
        )

        if not goal_terms:
            return 0.0

        text = memory.event.lower()

        matched = sum(
            term in text
            for term in goal_terms
        )

        return matched / len(goal_terms)

    def _current_goal_text(self, npc) -> str | None:
        goal = getattr(
            npc,
            "current_goal",
            None,
        )

        if goal is None:
            return None

        goal_type = getattr(
            goal,
            "goal_type",
            None,
        )

        if goal_type is None:
            return None

        return getattr(
            goal_type,
            "value",
            str(goal_type),
        )

    def _terms(self, text: str) -> set[str]:
        return {
            term
            for term in re.findall(
                r"[a-z0-9]+",
                text.lower(),
            )
            if term
        }