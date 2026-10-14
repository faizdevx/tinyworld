"""Memory retrieval by a weighted score.

The weights start from v1's MemoryRetriever, with lexical overlap replaced by
embedding similarity. Unlike v1, a memory with no textual match can still be
retrieved when it is important or recent enough.
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from tinyworld.agents.memory import Memory
from tinyworld.core.time import hours_between

WEIGHTS = {
    "relevance": 0.50,
    "importance": 0.20,
    "recency": 0.15,
    "relationship": 0.10,
    "goal": 0.05,
}


@dataclass
class Scored:
    memory: Memory
    score: float
    parts: dict[str, float]


def _similarity(memory: Memory, vector: np.ndarray | None) -> float:
    if vector is None or memory.embedding is None:
        return 0.0
    return max(0.0, float(np.dot(memory.embedding, vector)))


def score(
    memory: Memory,
    *,
    query: np.ndarray | None,
    now: datetime,
    goal: np.ndarray | None = None,
    related: frozenset[str] = frozenset(),
    half_life_hours: float = 48.0,
    weights: dict[str, float] = WEIGHTS,
) -> Scored:
    age = max(0.0, hours_between(memory.sim_time, now))
    parts = {
        "relevance": _similarity(memory, query),
        "importance": memory.importance,
        "recency": 0.5 ** (age / half_life_hours),
        "relationship": 1.0 if related.intersection(memory.participants) else 0.0,
        "goal": _similarity(memory, goal),
    }
    total = sum(weights[name] * value for name, value in parts.items())
    return Scored(memory, total * (0.5 + 0.5 * memory.confidence), parts)


def retrieve(
    memories: list[Memory],
    *,
    query: np.ndarray | None,
    now: datetime,
    k: int = 8,
    goal: np.ndarray | None = None,
    related: frozenset[str] = frozenset(),
    half_life_hours: float = 48.0,
    weights: dict[str, float] = WEIGHTS,
) -> list[Scored]:
    """The ``k`` best memories, best first. Ties go to the more recent."""
    scored = [
        score(
            memory, query=query, now=now, goal=goal, related=related,
            half_life_hours=half_life_hours, weights=weights,
        )
        for memory in memories
    ]
    scored.sort(key=lambda s: (s.score, s.memory.created_seq), reverse=True)
    return scored[:k]
