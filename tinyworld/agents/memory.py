"""The memory stream: what each agent remembers, with importance and embeddings."""

import json
from datetime import datetime
from typing import Literal

import numpy as np
from pydantic import ConfigDict, Field

from tinyworld.core.state import Model
from tinyworld.core.store import Store
from tinyworld.llm import embed as emb
from tinyworld.llm.embed import Embedder
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext

MemoryKind = Literal["observation", "utterance_heard", "reflection", "plan", "summary"]
EPISODIC = ("observation", "utterance_heard")


class NewMemory(Model):
    kind: MemoryKind
    text: str = Field(min_length=1)
    created_seq: int
    sim_time: datetime
    importance: float = Field(default=0.3, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_events: list[int] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)


class Memory(NewMemory):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    id: str
    agent: str
    branch_id: str
    embedding: np.ndarray | None = Field(default=None, exclude=True)


class MemoryStore:
    def __init__(self, store: Store, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    def write(self, branch_id: str, agent: str, items: list[NewMemory]) -> list[Memory]:
        if not items:
            return []
        vectors = self.embedder.embed([item.text for item in items])
        counts: dict[int, int] = {}
        written: list[Memory] = []
        rows = []
        for item, vector in zip(items, vectors):
            if item.created_seq not in counts:
                counts[item.created_seq] = self.store.query(
                    "SELECT COUNT(*) AS n FROM memories WHERE branch_id=? AND agent=?"
                    " AND created_seq=?",
                    (branch_id, agent, item.created_seq),
                )[0]["n"]
            ordinal = counts[item.created_seq]
            counts[item.created_seq] += 1
            memory = Memory(
                **item.model_dump(),
                id=f"{branch_id}:{agent}:{item.created_seq}:{ordinal}",
                agent=agent,
                branch_id=branch_id,
                embedding=vector,
            )
            written.append(memory)
            rows.append(
                (
                    memory.id, branch_id, agent, memory.created_seq,
                    memory.sim_time.isoformat(), memory.kind, memory.text,
                    memory.importance, emb.to_bytes(vector),
                    json.dumps(memory.source_events), memory.confidence,
                    json.dumps(memory.participants),
                )
            )
        self.store.executemany(
            "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        return written

    def list(
        self,
        branch_id: str,
        agent: str,
        *,
        kinds: tuple[str, ...] | None = None,
        after_seq: int = -1,
        include_superseded: bool = False,
        newest_first: bool = False,
        limit: int | None = None,
    ) -> list[Memory]:
        clause, params = self.store.lineage_clause(branch_id, "created_seq")
        sql = f"SELECT * FROM memories WHERE {clause} AND agent=? AND created_seq>?"
        params += [agent, after_seq]
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += list(kinds)
        if not include_superseded:
            gone, gone_params = self.store.lineage_clause(branch_id, "at_seq")
            sql += f" AND id NOT IN (SELECT memory_id FROM memory_supersedes WHERE {gone})"
            params += gone_params
        sql += (
            " ORDER BY created_seq DESC, rowid DESC"
            if newest_first
            else " ORDER BY created_seq, rowid"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [self._memory(row) for row in self.store.query(sql, params)]

    def latest(self, branch_id: str, agent: str, kind: str) -> Memory | None:
        found = self.list(branch_id, agent, kinds=(kind,), newest_first=True, limit=1)
        return found[0] if found else None

    def supersede(
        self, branch_id: str, memory_ids: list[str], by_id: str, at_seq: int
    ) -> None:
        self.store.executemany(
            "INSERT OR REPLACE INTO memory_supersedes VALUES (?,?,?,?)",
            [(branch_id, memory_id, by_id, at_seq) for memory_id in memory_ids],
        )

    @staticmethod
    def _memory(row) -> Memory:
        return Memory(
            id=row["id"],
            agent=row["agent"],
            branch_id=row["branch_id"],
            kind=row["kind"],
            text=row["text"],
            created_seq=row["created_seq"],
            sim_time=datetime.fromisoformat(row["sim_time"]),
            importance=row["importance"],
            confidence=row["confidence"],
            source_events=json.loads(row["source_events_json"]),
            participants=json.loads(row["participants_json"]),
            embedding=emb.from_bytes(row["embedding"]) if row["embedding"] else None,
        )


class Scores(Model):
    scores: list[int]


IMPORTANCE_SYSTEM = """You rate how much each new experience matters to one person, \
from 1 (routine, soon forgotten) to 10 (life-changing). Judge from that person's \
point of view: their goals, fears and relationships. Most everyday events are 1 to 3. \
Return one score per numbered experience, in order."""


def heuristic_importance(text: str, addressed: bool = False) -> float:
    """Importance when no model is available or its reply is unusable."""
    score = 0.3
    if addressed:
        score += 0.2
    lowered = text.lower()
    if any(word in lowered for word in ("dead", "kill", "attack", "arrest", "fire", "die")):
        score += 0.4
    return min(score, 1.0)


class ImportanceScorer:
    def __init__(self, llm: StructuredLLM | None) -> None:
        self.llm = llm

    async def score(
        self,
        who: str,
        texts: list[str],
        context: CallContext,
        *,
        addressed: list[bool] | None = None,
    ) -> list[float]:
        """Importance in 0..1 for each text, from the point of view of ``who``."""
        addressed = addressed or [False] * len(texts)
        fallback = [heuristic_importance(t, a) for t, a in zip(texts, addressed)]
        if not texts or self.llm is None:
            return fallback
        numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(texts))
        reply = await self.llm.call(
            "memory.importance",
            Scores,
            system=IMPORTANCE_SYSTEM,
            user=f"{who}\n\nNew experiences:\n{numbered}",
            context=context,
            fallback=Scores(scores=[]),
            max_tokens=500,
            check=lambda s: None
            if len(s.scores) == len(texts)
            else f"expected {len(texts)} scores, got {len(s.scores)}",
        )
        if not reply.ok:
            return fallback
        return [min(max(score, 1), 10) / 10 for score in reply.value.scores]


class Summary(Model):
    text: str = Field(min_length=1)
    importance: int = Field(default=3, ge=1, le=10)


SUMMARY_SYSTEM = """You compress one person's older memories into a single short \
paragraph they could plausibly recall later. Keep names, places and anything that \
changed a relationship or a belief. Drop routine detail. Write in the third person."""


class Compactor:
    """Merges old low-importance memories into summaries so retrieval stays sharp."""

    def __init__(
        self,
        llm: StructuredLLM | None,
        memory: MemoryStore,
        *,
        max_active: int = 60,
        batch: int = 20,
        keep_importance: float = 0.6,
    ) -> None:
        self.llm = llm
        self.memory = memory
        self.max_active = max_active
        self.batch = batch
        self.keep_importance = keep_importance

    async def compact(
        self, branch_id: str, agent: str, who: str, at_seq: int, now: datetime,
        context: CallContext,
    ) -> Memory | None:
        active = self.memory.list(branch_id, agent, kinds=EPISODIC)
        if len(active) <= self.max_active:
            return None
        # Important memories are never merged away.
        candidates = [m for m in active if m.importance < self.keep_importance]
        chosen = candidates[: self.batch]
        if len(chosen) < 2:
            return None
        fallback = Summary(
            text="Earlier: " + " ".join(m.text for m in chosen)[:600], importance=2
        )
        summary = fallback
        if self.llm is not None:
            reply = await self.llm.call(
                "memory.summarize",
                Summary,
                system=SUMMARY_SYSTEM,
                user=f"{who}\n\nMemories, oldest first:\n"
                + "\n".join(f"- {m.text}" for m in chosen),
                context=context,
                fallback=fallback,
                max_tokens=600,
            )
            summary = reply.value
        participants = list(dict.fromkeys(p for m in chosen for p in m.participants))
        written = self.memory.write(
            branch_id,
            agent,
            [
                NewMemory(
                    kind="summary",
                    text=summary.text,
                    created_seq=at_seq,
                    sim_time=now,
                    importance=summary.importance / 10,
                    source_events=sorted({s for m in chosen for s in m.source_events}),
                    participants=participants,
                )
            ],
        )[0]
        self.memory.supersede(branch_id, [m.id for m in chosen], written.id, at_seq)
        return written
