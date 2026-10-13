"""What agents believe, where they got it, and how it compares with the truth.

Ported from v1: a belief is (subject, predicate, value) with a confidence and a
source. Speech transfers claims, not facts, so a trusted liar produces a
confident false belief.
"""

import json
from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from tinyworld.core.state import Model, WorldState
from tinyworld.core.store import Store
from tinyworld.gm.perception import Observation

Origin = Literal["observation", "communication", "inference", "prior"]


class Belief(Model):
    agent: str
    subject: str
    predicate: str
    value: JsonValue = None
    confidence: float = Field(ge=0.0, le=1.0)
    source: str | None = None
    origin: Origin
    evidence: list[str] = Field(default_factory=list)
    as_of_seq: int
    as_of: datetime


class Comparison(Model):
    agent: str
    subject: str
    predicate: str
    believed: JsonValue = None
    actual: JsonValue = None
    truth_known: bool
    correct: bool | None
    confidence: float
    source: str | None = None
    origin: Origin


def trust(state: WorldState, listener: str, speaker: str) -> float:
    """How far ``listener`` takes ``speaker`` at their word, from 0.1 to 0.95."""
    relation = state.relation(listener, speaker)
    value = relation.value if relation is not None else 0
    return min(0.95, max(0.1, 0.5 + value / 200))


class BeliefStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def add(self, branch_id: str, belief: Belief) -> None:
        self.store.execute(
            "INSERT INTO beliefs (branch_id, agent, subject, predicate, value_json,"
            " confidence, source, origin, evidence_json, as_of_seq, as_of)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                branch_id, belief.agent, belief.subject, belief.predicate,
                json.dumps(belief.value), belief.confidence, belief.source,
                belief.origin, json.dumps(belief.evidence), belief.as_of_seq,
                belief.as_of.isoformat(),
            ),
        )

    def current(self, branch_id: str, agent: str | None = None) -> list[Belief]:
        """The latest belief for each (agent, subject, predicate)."""
        clause, params = self.store.lineage_clause(branch_id, "as_of_seq")
        sql = f"SELECT * FROM beliefs WHERE {clause}"
        if agent is not None:
            sql += " AND agent=?"
            params.append(agent)
        sql += " ORDER BY as_of_seq, row_id"
        latest: dict[tuple[str, str, str], Belief] = {}
        for row in self.store.query(sql, params):
            belief = Belief(
                agent=row["agent"],
                subject=row["subject"],
                predicate=row["predicate"],
                value=json.loads(row["value_json"]),
                confidence=row["confidence"],
                source=row["source"],
                origin=row["origin"],
                evidence=json.loads(row["evidence_json"]),
                as_of_seq=row["as_of_seq"],
                as_of=datetime.fromisoformat(row["as_of"]),
            )
            latest[(belief.agent, belief.subject, belief.predicate)] = belief
        return list(latest.values())

    def get(self, branch_id: str, agent: str, subject: str, predicate: str) -> Belief | None:
        for belief in self.current(branch_id, agent):
            if belief.subject == subject and belief.predicate == predicate:
                return belief
        return None

    def _consider(self, branch_id: str, candidate: Belief) -> bool:
        """Adopt ``candidate`` unless a better-founded belief already stands."""
        existing = self.get(branch_id, candidate.agent, candidate.subject, candidate.predicate)
        if existing is not None and existing.value == candidate.value:
            if candidate.confidence <= existing.confidence:
                return False
        elif existing is not None:
            # Seeing beats hearing. Otherwise the more confident source wins,
            # with a little give so fresh news can displace stale certainty.
            seen_before = existing.origin == "observation"
            seen_now = candidate.origin == "observation"
            if seen_before and not seen_now:
                return False
            if seen_before == seen_now and candidate.confidence < existing.confidence - 0.1:
                return False
        self.add(branch_id, candidate)
        return True

    def update_from_observation(
        self,
        branch_id: str,
        state: WorldState,
        observation: Observation,
        memory_id: str | None = None,
    ) -> list[Belief]:
        """Beliefs an observer forms from what they saw and what they were told."""
        evidence = [memory_id] if memory_id else []
        adopted: list[Belief] = []

        def consider(subject, predicate, value, confidence, source, origin) -> None:
            belief = Belief(
                agent=observation.observer,
                subject=subject,
                predicate=predicate,
                value=value,
                confidence=round(min(1.0, max(0.0, confidence)), 3),
                source=source,
                origin=origin,
                evidence=evidence,
                as_of_seq=observation.event_seq,
                as_of=observation.sim_time,
            )
            if self._consider(branch_id, belief):
                adopted.append(belief)

        for fact in observation.facts:
            consider(
                fact.subject, fact.predicate, fact.value,
                observation.confidence, None, "observation",
            )

        speaker = observation.speaker
        if speaker and speaker != observation.observer:
            weight = observation.confidence * trust(state, observation.observer, speaker)
            for claim in observation.claims:
                consider(
                    claim.subject, claim.predicate, claim.value,
                    weight, speaker, "communication",
                )
        return adopted


def truth(state: WorldState, subject: str, predicate: str) -> tuple[bool, JsonValue]:
    """(known, value) for a statement, read from world state."""
    entity = state.entities.get(subject)
    if entity is not None:
        if predicate == "location":
            return True, entity.location
        if predicate == "alive":
            return True, entity.alive
        if predicate.startswith("has:"):
            return True, entity.inventory.get(predicate[4:], 0)
        if predicate in entity.attrs:
            return True, entity.attrs[predicate]
    for fact in state.active_facts():
        if fact.subject == subject and fact.predicate == predicate:
            return True, fact.value
    return False, None


def compare_beliefs(
    state: WorldState, beliefs: list[Belief]
) -> list[Comparison]:
    """Each belief next to what is actually true, where the world can say."""
    comparisons = []
    for belief in beliefs:
        known, actual = truth(state, belief.subject, belief.predicate)
        comparisons.append(
            Comparison(
                agent=belief.agent,
                subject=belief.subject,
                predicate=belief.predicate,
                believed=belief.value,
                actual=actual,
                truth_known=known,
                correct=(belief.value == actual) if known else None,
                confidence=belief.confidence,
                source=belief.source,
                origin=belief.origin,
            )
        )
    return comparisons
