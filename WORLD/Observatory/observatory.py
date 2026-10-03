from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Interventions.models import GodIntervention


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _json_safe(value, _seen: set[int] | None = None):
    if _seen is None:
        _seen = set()

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, _seen) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, _seen) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_safe(item, _seen) for item in sorted(value, key=lambda item: str(item))]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict(), _seen)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dict__") and not isinstance(value, (str, int, float, bool, type(None))):
        obj_id = id(value)
        if obj_id in _seen:
            return f"<recursive:{type(value).__name__}>"
        _seen.add(obj_id)
        try:
            return {str(key): _json_safe(item, _seen) for key, item in vars(value).items() if not key.startswith("_")}
        finally:
            _seen.remove(obj_id)
    return value


@dataclass(frozen=True)
class BeliefSnapshot:
    subject: str
    predicate: str
    value: object
    source: str | None = None
    origin_type: str | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _freeze(self.value))
        if not self.subject.strip():
            raise ValueError("Belief subject cannot be empty")
        if not self.predicate.strip():
            raise ValueError("Belief predicate cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Belief confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class NPCSnapshot:
    name: str
    role: str
    location: str | None
    money: int
    personality: Mapping[str, object]
    knowledge: tuple[dict[str, object], ...]
    memory: tuple[dict[str, object], ...]
    current_goal: str | None
    current_plan: str | None
    current_action: str | None
    relationships: tuple[dict[str, object], ...]
    beliefs: tuple[BeliefSnapshot, ...]
    social_memory: tuple[dict[str, object], ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "personality", _freeze(dict(self.personality)))
        object.__setattr__(self, "knowledge", tuple(_freeze(item) for item in self.knowledge))
        object.__setattr__(self, "memory", tuple(_freeze(item) for item in self.memory))
        object.__setattr__(self, "relationships", tuple(_freeze(item) for item in self.relationships))
        object.__setattr__(self, "beliefs", tuple(self.beliefs))
        object.__setattr__(self, "social_memory", tuple(_freeze(item) for item in self.social_memory))
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))


@dataclass(frozen=True)
class WorldSnapshot:
    timestamp: tuple[int, int]
    metadata: Mapping[str, object]
    resources: Mapping[str, object]
    buildings: tuple[str, ...]
    entities: tuple[dict[str, object], ...]
    factions: tuple[str, ...]
    npcs: tuple[NPCSnapshot, ...]
    events: tuple[dict[str, object], ...]
    environment: Mapping[str, object]
    economy: Mapping[str, object]
    intervention_history: tuple[dict[str, object], ...]
    population: int
    seed: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))
        object.__setattr__(self, "resources", _freeze(dict(self.resources)))
        object.__setattr__(self, "buildings", tuple(self.buildings))
        object.__setattr__(self, "entities", tuple(_freeze(item) for item in self.entities))
        object.__setattr__(self, "factions", tuple(self.factions))
        object.__setattr__(self, "npcs", tuple(self.npcs))
        object.__setattr__(self, "events", tuple(_freeze(item) for item in self.events))
        object.__setattr__(self, "environment", _freeze(dict(self.environment)))
        object.__setattr__(self, "economy", _freeze(dict(self.economy)))
        object.__setattr__(self, "intervention_history", tuple(_freeze(item) for item in self.intervention_history))


@dataclass(frozen=True)
class RealityComparison:
    npc_name: str
    subject: str
    predicate: str
    world_value: object
    npc_value: object
    known: bool
    source: str | None = None
    error: object = None
    absolute_error: object = None
    relative_error: object = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_value", _freeze(self.world_value))
        object.__setattr__(self, "npc_value", _freeze(self.npc_value))


@dataclass(frozen=True)
class Metric:
    name: str
    value: object
    definition: str


@dataclass(frozen=True)
class ExperimentMetrics:
    metrics: tuple[Metric, ...]

    def as_dict(self) -> dict[str, object]:
        return {metric.name: metric.value for metric in self.metrics}

    def __getitem__(self, key: str) -> object:
        return self.as_dict()[key]

    def __iter__(self):
        return iter(self.as_dict())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ExperimentMetrics):
            return self.as_dict() == other.as_dict()
        if isinstance(other, dict):
            return self.as_dict() == other
        return super().__eq__(other)


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    seed: int
    scenario: WorldScenario | dict[str, Any]
    interventions: tuple[GodIntervention, ...] = ()
    snapshots: tuple[WorldSnapshot, ...] = ()
    metrics: ExperimentMetrics | dict[str, object] = field(default_factory=dict)
    description: str | None = None
    configuration: dict[str, object] = field(default_factory=dict)
    start_time: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.scenario, Mapping):
            object.__setattr__(self, "scenario", WorldScenario(**dict(self.scenario)))
        elif self.scenario is None:
            object.__setattr__(self, "scenario", WorldScenario())
        object.__setattr__(self, "interventions", tuple(self.interventions))
        object.__setattr__(self, "snapshots", tuple(self.snapshots))
        if isinstance(self.metrics, dict):
            object.__setattr__(self, "metrics", ExperimentMetrics(tuple(Metric(name=str(k), value=v, definition="") for k, v in self.metrics.items())))
        elif self.metrics is None:
            object.__setattr__(self, "metrics", ExperimentMetrics(()))
        object.__setattr__(self, "configuration", _freeze(dict(self.configuration)))
        if self.start_time is None:
            object.__setattr__(self, "start_time", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "seed": self.seed,
            "scenario": _json_safe(self.scenario),
            "interventions": [_json_safe(item) for item in self.interventions],
            "snapshots": [_json_safe(item) for item in self.snapshots],
            "metrics": self.metrics.as_dict() if isinstance(self.metrics, ExperimentMetrics) else dict(self.metrics),
            "description": self.description,
            "configuration": _json_safe(self.configuration),
            "start_time": self.start_time,
        }


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    seed: int
    scenario: dict[str, Any]
    clock: dict[str, int]
    world_state: Mapping[str, object]
    npc_state: tuple[dict[str, object], ...]
    event_state: tuple[dict[str, object], ...]
    rng_state: Mapping[str, object]
    intervention_history: tuple[dict[str, object], ...]
    timestamp: tuple[int, int] = (1, 0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_state", _freeze(dict(self.world_state)))
        object.__setattr__(self, "npc_state", tuple(_freeze(item) for item in self.npc_state))
        object.__setattr__(self, "event_state", tuple(_freeze(item) for item in self.event_state))
        object.__setattr__(self, "rng_state", _freeze(dict(self.rng_state)))
        object.__setattr__(self, "intervention_history", tuple(_freeze(item) for item in self.intervention_history))
        object.__setattr__(self, "scenario", _freeze(dict(self.scenario)))
        object.__setattr__(self, "clock", _freeze(dict(self.clock)))

    def to_json(self) -> str:
        return json.dumps(_json_safe(self.to_dict()), sort_keys=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "seed": self.seed,
            "scenario": _json_safe(self.scenario),
            "clock": _json_safe(self.clock),
            "world_state": _json_safe(self.world_state),
            "npc_state": _json_safe(self.npc_state),
            "event_state": _json_safe(self.event_state),
            "rng_state": _json_safe(self.rng_state),
            "intervention_history": _json_safe(self.intervention_history),
            "timestamp": list(self.timestamp),
        }

    @classmethod
    def from_json(cls, payload: str) -> "Checkpoint":
        data = json.loads(payload)
        return cls(
            checkpoint_id=data["checkpoint_id"],
            seed=data["seed"],
            scenario=data.get("scenario", {}),
            clock=data.get("clock", {"day": 1, "hour": 0}),
            world_state=data.get("world_state", {}),
            npc_state=tuple(data.get("npc_state", ())),
            event_state=tuple(data.get("event_state", ())),
            rng_state=data.get("rng_state", {}),
            intervention_history=tuple(data.get("intervention_history", ())),
            timestamp=tuple(data.get("timestamp", (1, 0))),
        )


class Observatory:
    """Read-only research interface for TinyWorld."""

    def inspect_world(self, world) -> WorldSnapshot:
        world_state = getattr(world, "metadata", {})
        resource_state = {
            name: getattr(resource, "quantity", resource)
            for name, resource in getattr(world, "resources", {}).items()
        }
        buildings = tuple(getattr(building, "name", str(building)) for building in getattr(world, "buildings", []))
        entities = tuple(
            {
                "name": getattr(entity, "name", "unknown"),
                "entity_type": getattr(entity, "entity_type", "unknown"),
                "location": getattr(entity, "location", None),
                "properties": _json_safe(getattr(entity, "properties", {})),
            }
            for entity in getattr(world, "entities", [])
        )
        factions = tuple(getattr(faction, "name", str(faction)) for faction in getattr(world, "factions", []))
        npcs = tuple(self.inspect_npc(world, npc) for npc in getattr(world, "npcs", []))
        events = tuple(
            {
                "sequence": getattr(event, "sequence", index + 1),
                "event_type": getattr(event, "event_type", "unknown"),
                "actor": getattr(event, "actor", ""),
                "target": getattr(event, "target", None),
                "description": getattr(event, "description", ""),
                "properties": _json_safe(getattr(event, "properties", {})),
            }
            for index, event in enumerate(getattr(getattr(world, "event_log", None), "events", []))
        )
        env_state = {}
        environment_system = getattr(world, "environment_system", None)
        if environment_system is not None:
            env_state = {
                "random_events_enabled": getattr(environment_system, "random_events_enabled", False),
                "weather": getattr(environment_system, "weather", None),
            }
        economy = {
            "shop_name": getattr(getattr(world, "shop", None), "name", None),
            "shop_food": getattr(getattr(world, "shop", None), "food", 0),
            "shop_money": getattr(getattr(world, "shop", None), "money", 0),
        }
        intervention_history = tuple(
            {
                "day": getattr(audit, "day", 0),
                "hour": getattr(audit, "hour", 0),
                "operation": getattr(getattr(audit, "intervention", None), "operation", None),
                "target": getattr(getattr(audit, "intervention", None), "target", None),
                "result": getattr(getattr(audit, "result", None), "success", None),
            }
            for audit in getattr(world, "intervention_history", [])
        )
        seed = getattr(getattr(world, "rng", None), "seed", None)
        return WorldSnapshot(
            timestamp=(getattr(getattr(world, "clock", None), "day", 1), getattr(getattr(world, "clock", None), "hour", 0)),
            metadata=dict(world_state),
            resources=resource_state,
            buildings=buildings,
            entities=entities,
            factions=factions,
            npcs=npcs,
            events=events,
            environment=env_state,
            economy=economy,
            intervention_history=intervention_history,
            population=len(getattr(world, "npcs", [])),
            seed=seed,
        )

    def inspect_npc(self, world, npc_id) -> NPCSnapshot:
        npc = self._resolve_npc(world, npc_id)
        personality = getattr(npc, "personality", None)
        if personality is None:
            personality = {}
        elif hasattr(personality, "__dict__"):
            personality = {key: value for key, value in vars(personality).items() if not key.startswith("_")}
        knowledge = tuple({
            "subject": entry.subject,
            "predicate": entry.predicate,
            "value": entry.value,
            "confidence": entry.confidence,
        } for entry in getattr(npc, "knowledge", []))
        memory = tuple({
            "day": getattr(mem, "day", 0),
            "hour": getattr(mem, "hour", 0),
            "event": getattr(mem, "event", ""),
            "importance": getattr(mem, "importance", 0),
            "memory_type": getattr(mem, "memory_type", "event"),
            "participants": list(getattr(mem, "participants", [])),
        } for mem in getattr(npc, "memories", []))
        relationships = tuple({
            "npc": name,
            "value": relationship.value,
        } for name, relationship in getattr(npc, "relationships", {}).items())
        social_memory = tuple({
            "person": person,
            "count": len(entries),
        } for person, entries in getattr(getattr(npc, "social_memory", None), "_memories_by_person", {}).items())
        beliefs = tuple(
            BeliefSnapshot(
                subject=getattr(belief, "subject", "unknown"),
                predicate=getattr(belief, "predicate", "unknown"),
                value=getattr(belief, "value", None),
                source=getattr(belief, "source", None),
                origin_type=getattr(belief, "origin_type", None),
                confidence=getattr(belief, "confidence", 0.0),
            )
            for belief in getattr(npc, "beliefs", [])
        )
        return NPCSnapshot(
            name=npc.name,
            role=getattr(npc, "role", "unknown"),
            location=getattr(npc, "location", None),
            money=getattr(npc, "money", 0),
            personality=personality,
            knowledge=knowledge,
            memory=memory,
            current_goal=getattr(getattr(npc, "current_goal", None), "goal_type", None),
            current_plan=getattr(getattr(npc, "active_plan", None), "goal_type", None),
            current_action=getattr(getattr(npc, "current_action", None), "name", None),
            relationships=relationships,
            beliefs=beliefs,
            social_memory=social_memory,
            metadata={
                "food": getattr(npc, "food", 0),
                "energy": getattr(npc, "energy", 0),
                "hunger": getattr(npc, "hunger", 0),
                "home": getattr(npc, "home", None),
            },
        )

    def snapshot(self, world) -> WorldSnapshot:
        return self.inspect_world(world)

    def compare_beliefs(self, world) -> list[RealityComparison]:
        world_truth = self._world_truth_index(world)
        comparisons = []
        seen = set()
        for npc in getattr(world, "npcs", []):
            belief_index = {
                (str(getattr(belief, "subject", "")).strip(), str(getattr(belief, "predicate", "")).strip()): belief
                for belief in getattr(npc, "beliefs", [])
            }
            for subject, predicate in self._candidate_truth_subjects(world):
                key = (subject, predicate)
                belief = belief_index.get(key)
                world_value = world_truth.get(key)
                known = belief is not None
                npc_value = getattr(belief, "value", None) if belief is not None else None
                source = getattr(belief, "source", None) if belief is not None else None
                error = None
                absolute_error = None
                relative_error = None
                if known and isinstance(world_value, (int, float)) and isinstance(npc_value, (int, float)):
                    error = npc_value - world_value
                    absolute_error = abs(error)
                    relative_error = absolute_error / abs(world_value) if abs(world_value) else None
                comparison = RealityComparison(
                    npc_name=npc.name,
                    subject=subject,
                    predicate=predicate,
                    world_value=world_value,
                    npc_value=npc_value,
                    known=known,
                    source=source,
                    error=error,
                    absolute_error=absolute_error,
                    relative_error=relative_error,
                )
                comparisons.append(comparison)
                seen.add((npc.name, subject, predicate))

        # Preserve explicit belief entries for any non-world-truth record that still exists.
        for npc in getattr(world, "npcs", []):
            for belief in getattr(npc, "beliefs", []):
                key = (npc.name, str(getattr(belief, "subject", "")).strip(), str(getattr(belief, "predicate", "")).strip())
                if key in seen:
                    continue
                world_value = world_truth.get((str(getattr(belief, "subject", "")).strip(), str(getattr(belief, "predicate", "")).strip()))
                comparisons.append(
                    RealityComparison(
                        npc_name=npc.name,
                        subject=str(belief.subject),
                        predicate=str(belief.predicate),
                        world_value=world_value,
                        npc_value=getattr(belief, "value", None),
                        known=True,
                        source=getattr(belief, "source", None),
                        error=None,
                        absolute_error=None,
                        relative_error=None,
                    )
                )
        return comparisons

    def metrics(self, world) -> ExperimentMetrics:
        metrics = [
            Metric("population", len(getattr(world, "npcs", [])), "Number of NPCs in the world."),
            Metric("resource_levels", {name: getattr(resource, "quantity", 0) for name, resource in getattr(world, "resources", {}).items()}, "Current resource quantities."),
            Metric("event_count", len(getattr(getattr(world, "event_log", None), "events", [])), "Number of world events recorded."),
            Metric("intervention_count", len(getattr(world, "intervention_history", [])), "Number of God interventions recorded."),
            Metric("belief_count", sum(len(getattr(npc, "beliefs", [])) for npc in getattr(world, "npcs", [])), "Total NPC belief entries."),
            Metric("false_belief_count", self._count_false_beliefs(world), "Number of evaluated beliefs that conflict with known truth."),
            Metric("unknown_fact_count", self._count_unknown_facts(world), "Number of beliefs without a known world-truth comparison."),
        ]
        return ExperimentMetrics(tuple(metrics))

    def events(self, world, start_day: int | None = None, end_day: int | None = None):
        events = list(getattr(getattr(world, "event_log", None), "events", []))
        if start_day is None and end_day is None:
            return [self._event_summary(event) for event in events]
        filtered = []
        for event in events:
            day = getattr(event, "day", 1)
            if start_day is not None and day < start_day:
                continue
            if end_day is not None and day > end_day:
                continue
            filtered.append(self._event_summary(event))
        return filtered

    def save_checkpoint(self, world, checkpoint_id: str, path: str | None = None) -> Checkpoint:
        checkpoint = self.build_checkpoint(world, checkpoint_id)
        target = Path(path) if path is not None else Path(f"{checkpoint_id}.json")
        target.write_text(checkpoint.to_json(), encoding="utf-8")
        return checkpoint

    def load_checkpoint(self, path: str | Path) -> Checkpoint:
        payload = Path(path).read_text(encoding="utf-8")
        return Checkpoint.from_json(payload)

    def build_checkpoint(self, world, checkpoint_id: str) -> Checkpoint:
        world_snapshot = self.inspect_world(world)
        npc_state = [
            {
                "name": npc.name,
                "role": getattr(npc, "role", "unknown"),
                "location": getattr(npc, "location", None),
                "money": getattr(npc, "money", 0),
                "beliefs": [self._belief_to_dict(b) for b in getattr(npc, "beliefs", [])],
                "memories": [self._memory_to_dict(m) for m in getattr(npc, "memories", [])],
            }
            for npc in getattr(world, "npcs", [])
        ]
        event_state = [
            {
                "sequence": getattr(event, "sequence", index + 1),
                "event_type": getattr(event, "event_type", "unknown"),
                "actor": getattr(event, "actor", ""),
                "target": getattr(event, "target", None),
                "description": getattr(event, "description", ""),
            }
            for index, event in enumerate(getattr(getattr(world, "event_log", None), "events", []))
        ]
        rng_state = {"seed": getattr(getattr(world, "rng", None), "seed", None)}
        return Checkpoint(
            checkpoint_id=checkpoint_id,
            seed=getattr(getattr(world, "rng", None), "seed", 0),
            scenario=_json_safe(getattr(world, "metadata", {})),
            clock={"day": getattr(getattr(world, "clock", None), "day", 1), "hour": getattr(getattr(world, "clock", None), "hour", 0)},
            world_state={
                "metadata": _json_safe(world_snapshot.metadata),
                "resources": _json_safe(world_snapshot.resources),
                "buildings": list(world_snapshot.buildings),
                "entities": _json_safe(world_snapshot.entities),
                "population": world_snapshot.population,
            },
            npc_state=tuple(npc_state),
            event_state=tuple(event_state),
            rng_state=rng_state,
            intervention_history=tuple(
                {
                    "intervention": getattr(audit, "intervention", None),
                    "result": getattr(audit, "result", None),
                    "day": getattr(audit, "day", 0),
                    "hour": getattr(audit, "hour", 0),
                }
                for audit in getattr(world, "intervention_history", [])
            ),
            timestamp=world_snapshot.timestamp,
        )

    def record_intervention(self, world, intervention: GodIntervention) -> None:
        if not hasattr(world, "intervention_history"):
            world.intervention_history = []
        world.intervention_history.append({
            "operation": getattr(intervention, "operation", None),
            "target": getattr(intervention, "target", None),
            "properties": dict(getattr(intervention, "properties", {})),
        })

    @staticmethod
    def _resolve_npc(world, npc_id):
        if hasattr(npc_id, "name"):
            return npc_id
        if isinstance(npc_id, str):
            identifier = npc_id.removeprefix("npc:")
            for npc in getattr(world, "npcs", []):
                if npc.name == identifier:
                    return npc
        raise ValueError(f"NPC {npc_id} not found")

    def _world_truth_index(self, world):
        truth = {}
        for key, value in getattr(world, "metadata", {}).items():
            if key.endswith("strength"):
                truth[("foreign_army", "strength")] = value
            if key.endswith("size"):
                truth[("foreign_army", "size")] = value
        for entity in getattr(world, "entities", []):
            for field_name, value in getattr(entity, "properties", {}).items():
                subject = str(getattr(entity, "name", "")).lower().replace(" ", "_")
                truth[(subject, str(field_name))] = value
        for resource in getattr(world, "resources", {}).values():
            truth[(str(getattr(resource, "name", "resource")).lower(), "quantity")] = getattr(resource, "quantity", 0)
        return truth

    def _candidate_truth_subjects(self, world):
        subjects = []
        for key, value in self._world_truth_index(world).items():
            subjects.append((key[0], key[1]))
        return list(dict.fromkeys(subjects))

    def _world_truth_value(self, world, subject: str, predicate: str):
        truth = self._world_truth_index(world)
        return truth.get((str(subject).lower().replace(" ", "_"), str(predicate).lower()))

    def _count_false_beliefs(self, world) -> int:
        comparisons = self.compare_beliefs(world)
        count = 0
        for comparison in comparisons:
            if comparison.known and comparison.npc_value is not None and comparison.world_value != comparison.npc_value:
                count += 1
        return count

    def _count_unknown_facts(self, world) -> int:
        comparisons = self.compare_beliefs(world)
        return sum(1 for item in comparisons if not item.known)

    @staticmethod
    def _belief_to_dict(belief) -> dict[str, object]:
        return {
            "subject": getattr(belief, "subject", ""),
            "predicate": getattr(belief, "predicate", ""),
            "value": getattr(belief, "value", None),
            "confidence": getattr(belief, "confidence", 0.0),
            "source": getattr(belief, "source", None),
            "origin_type": getattr(belief, "origin_type", None),
        }

    @staticmethod
    def _memory_to_dict(memory) -> dict[str, object]:
        return {
            "day": getattr(memory, "day", 0),
            "hour": getattr(memory, "hour", 0),
            "event": getattr(memory, "event", ""),
            "importance": getattr(memory, "importance", 0),
            "memory_type": getattr(memory, "memory_type", "event"),
            "participants": list(getattr(memory, "participants", [])),
        }

    @staticmethod
    def _event_summary(event) -> dict[str, object]:
        return {
            "sequence": getattr(event, "sequence", 0),
            "event_type": getattr(event, "event_type", "unknown"),
            "actor": getattr(event, "actor", ""),
            "target": getattr(event, "target", None),
            "description": getattr(event, "description", ""),
            "properties": _json_safe(getattr(event, "properties", {})),
        }


class ExperimentRunner:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.observatory = Observatory()

    def run_experiment(
        self,
        *,
        experiment_id: str | None = None,
        scenario: WorldScenario | dict[str, Any] | None = None,
        interventions: Iterable[GodIntervention] | None = None,
        description: str | None = None,
    ) -> Experiment:
        scenario_obj = scenario if scenario is not None else WorldScenario()
        if not isinstance(scenario_obj, WorldScenario):
            scenario_obj = WorldScenario(**scenario_obj)
        world = WorldGenerator().generate(scenario_obj, seed=self.seed)
        appointment_interventions = list(interventions or [])
        for intervention in appointment_interventions:
            world.intervention_engine.apply(world, intervention)

        snapshots = (self.observatory.inspect_world(world),)
        metrics = self.observatory.metrics(world)
        experiment = Experiment(
            experiment_id=experiment_id or f"EXP-{self.seed:03d}",
            seed=self.seed,
            scenario=scenario_obj,
            interventions=tuple(appointment_interventions),
            snapshots=snapshots,
            metrics=metrics,
            description=description,
        )
        return experiment


__all__ = [
    "BeliefSnapshot",
    "Checkpoint",
    "Experiment",
    "ExperimentMetrics",
    "ExperimentRunner",
    "Metric",
    "NPCSnapshot",
    "Observatory",
    "RealityComparison",
    "WorldSnapshot",
]
