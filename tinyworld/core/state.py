"""World state. A pure fold over the event log; never mutated outside reducers."""

import heapq
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from tinyworld.core.ids import (
    EntityId,
    FactId,
    ProcessId,
    edge_key,
    parse_id,
    relation_key,
)

_FACT_ID = re.compile(r"^fact:[a-z0-9][a-z0-9_]*$")
_PROCESS_ID = re.compile(r"^process:[a-z0-9][a-z0-9_]*$")
_COMMITMENT_ID = re.compile(r"^commitment:[a-z0-9][a-z0-9_]*$")

EntityKind = Literal["person", "place", "item", "org", "faction", "resource"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Entity(Model):
    id: EntityId
    kind: EntityKind
    name: str = Field(min_length=1)
    location: EntityId | None = None
    attrs: dict[str, JsonValue] = Field(default_factory=dict)
    inventory: dict[EntityId, int] = Field(default_factory=dict)
    alive: bool = True

    @model_validator(mode="after")
    def _id_matches_kind(self):
        kind, _ = parse_id(self.id)
        if kind != self.kind:
            raise ValueError(f"id {self.id!r} does not match kind {self.kind!r}")
        return self


class PlaceEdge(Model):
    """A connection between two places."""

    travel_minutes: int = Field(default=10, gt=0)
    visible: bool = False
    audible: bool = False


class Relation(Model):
    kind: str = "acquaintance"
    value: int = Field(default=0, ge=-100, le=100)
    note: str = ""


class Fact(Model):
    """Something true about the world, such as "grain is rationed"."""

    id: FactId
    text: str = Field(min_length=1)
    subject: str | None = None
    predicate: str | None = None
    value: JsonValue = None
    public: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _valid_id(self):
        if not _FACT_ID.match(self.id):
            raise ValueError(f"invalid fact id: {self.id!r}")
        return self


class ProcessRequirements(Model):
    participants: list[EntityId] = Field(default_factory=list)
    items: dict[EntityId, int] = Field(default_factory=dict)
    facts: list[FactId] = Field(default_factory=list)
    min_workers: int = Field(default=1, ge=1)


class Process(Model):
    """A long-running effort that agents advance over many ticks."""

    id: ProcessId
    name: str = Field(min_length=1)
    owner: EntityId
    location: EntityId | None = None
    description: str = ""
    requirements: ProcessRequirements = Field(default_factory=ProcessRequirements)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    work_minutes: int = Field(default=600, gt=0)
    status: Literal["active", "completed", "abandoned", "failed"] = "active"
    outcome: Fact | None = None
    # An idea this undertaking sets out to work out; its workers learn it.
    teaches: str | None = None

    @model_validator(mode="after")
    def _valid_id(self):
        if not _PROCESS_ID.match(self.id):
            raise ValueError(f"invalid process id: {self.id!r}")
        return self


class Commitment(Model):
    """A promise one person made to another, to be kept by a time."""

    id: str
    by: EntityId
    to: EntityId
    kind: Literal["meet", "give"]
    text: str = Field(min_length=1)
    due: datetime
    made_at: datetime
    # The log position the promise was made at; later transfers count towards it.
    made_seq: int = Field(default=0, ge=0)
    place: EntityId | None = None
    item: EntityId | None = None
    quantity: int = Field(default=1, gt=0)
    status: Literal["open", "kept", "broken", "released"] = "open"

    @model_validator(mode="after")
    def _valid(self):
        if not _COMMITMENT_ID.match(self.id):
            raise ValueError(f"invalid commitment id: {self.id!r}")
        if self.kind == "meet" and self.place is None:
            raise ValueError("a meeting promise needs a place")
        if self.kind == "give" and self.item is None:
            raise ValueError("a promise to give needs an item")
        return self


class WorldState(Model):
    sim_time: datetime
    entities: dict[EntityId, Entity] = Field(default_factory=dict)
    edges: dict[str, PlaceEdge] = Field(default_factory=dict)
    relations: dict[str, Relation] = Field(default_factory=dict)
    facts: dict[FactId, Fact] = Field(default_factory=dict)
    processes: dict[ProcessId, Process] = Field(default_factory=dict)
    commitments: dict[str, Commitment] = Field(default_factory=dict)
    rules: dict[str, JsonValue] = Field(default_factory=dict)
    seq: int = 0

    # -- queries ---------------------------------------------------------

    def get(self, entity_id: EntityId) -> Entity | None:
        return self.entities.get(entity_id)

    def people(self, *, alive: bool = True) -> list[Entity]:
        return [
            entity
            for entity in self.entities.values()
            if entity.kind == "person" and (entity.alive or not alive)
        ]

    def people_at(self, place: EntityId, *, alive: bool = True) -> list[Entity]:
        return [p for p in self.people(alive=alive) if p.location == place]

    def things_at(self, place: EntityId) -> list[Entity]:
        return [
            entity
            for entity in self.entities.values()
            if entity.location == place and entity.kind != "person"
        ]

    def edge(self, a: EntityId, b: EntityId) -> PlaceEdge | None:
        return self.edges.get(edge_key(a, b))

    def neighbors(self, place: EntityId) -> dict[EntityId, PlaceEdge]:
        found: dict[EntityId, PlaceEdge] = {}
        for key, edge in self.edges.items():
            first, second = key.split("|")
            if first == place:
                found[second] = edge
            elif second == place:
                found[first] = edge
        return found

    def relation(self, source: EntityId, dest: EntityId) -> Relation | None:
        return self.relations.get(relation_key(source, dest))

    def open_commitments(self, person: EntityId | None = None) -> list[Commitment]:
        found = [c for c in self.commitments.values() if c.status == "open"]
        if person is not None:
            found = [c for c in found if person in (c.by, c.to)]
        return sorted(found, key=lambda c: (c.due, c.id))

    def active_facts(self) -> list[Fact]:
        return [
            fact
            for fact in self.facts.values()
            if fact.valid_to is None or fact.valid_to > self.sim_time
        ]

    def fact_holds(self, fact_id: FactId) -> bool:
        fact = self.facts.get(fact_id)
        return fact is not None and (
            fact.valid_to is None or fact.valid_to > self.sim_time
        )

    def path(self, start: EntityId, goal: EntityId) -> tuple[list[EntityId], int] | None:
        """Shortest route by travel time. Returns (places, minutes) or None."""
        if start == goal:
            return [start], 0
        adjacency: dict[EntityId, list[tuple[EntityId, int]]] = {}
        for key, edge in self.edges.items():
            first, second = key.split("|")
            adjacency.setdefault(first, []).append((second, edge.travel_minutes))
            adjacency.setdefault(second, []).append((first, edge.travel_minutes))
        best = {start: 0}
        previous: dict[EntityId, EntityId] = {}
        queue = [(0, start)]
        while queue:
            cost, node = heapq.heappop(queue)
            if node == goal:
                route = [goal]
                while route[-1] != start:
                    route.append(previous[route[-1]])
                return route[::-1], cost
            if cost > best.get(node, cost):
                continue
            for neighbor, minutes in adjacency.get(node, []):
                candidate = cost + minutes
                if candidate < best.get(neighbor, candidate + 1):
                    best[neighbor] = candidate
                    previous[neighbor] = node
                    heapq.heappush(queue, (candidate, neighbor))
        return None
