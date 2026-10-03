from __future__ import annotations

import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from WORLD.Buildings.buildings import Building
from WORLD.Communication.communication import MessageProposal, MessageType
from WORLD.Events.event import WorldEvent
from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Interventions.models import GodIntervention, InterventionOperation, InterventionVisibility
from WORLD.NPCs.npc import NPC
from WORLD.Observatory import Observatory
from WORLD.Observatory.observatory import _json_safe
from WORLD.Resources.food import Resource
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CHECKPOINT_DIR = BASE_DIR.parent / ".tinyworld_checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True, parents=True)


class InterventionRequest(BaseModel):
    operation: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)
    value: Any = None
    visibility: str = InterventionVisibility.GOD_ONLY.value

    model_config = {"arbitrary_types_allowed": True}


class CheckpointRequest(BaseModel):
    checkpoint_id: str


def _safe_json(value: Any) -> Any:
    return _json_safe(value)


class AppState:
    def __init__(self) -> None:
        self.experiment_id = "EXP-001"
        self.seed = 42
        self.scenario = WorldScenario(
            era="15th-century frontier settlement",
            geography="Northern Road valley",
            climate="temperate",
            population=50,
            resources={"Food": 100},
            buildings=["House", "Village Farm", "General Store", "Workshop"],
            factions=["Village Council", "Merchant Guild"],
            landmarks=["Forest", "River", "Northern Road"],
        )
        self.lock = threading.RLock()
        self.running = False
        self._thread: threading.Thread | None = None
        self.observatory = Observatory()
        self.world = self._build_world()
        self.simulation = Simulation(self.world)
        self.snapshots: list[dict[str, Any]] = []
        self.checkpoint_store: dict[str, str] = {}
        self.last_snapshot: dict[str, Any] | None = None

    def _build_world(self) -> World:
        return WorldGenerator().generate(self.scenario, seed=self.seed)

    def _stop_loop(self) -> None:
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def _simulation_runner(self) -> None:
        while self.running:
            time.sleep(1.0)
            with self.lock:
                if not self.running:
                    break
                self.simulation.tick()

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self.running:
                raise RuntimeError("Simulation is already running.")
            self.running = True
            self._thread = threading.Thread(target=self._simulation_runner, daemon=True)
            self._thread.start()
            return self.get_status()

    def pause(self) -> dict[str, Any]:
        with self.lock:
            self.running = False
            if self._thread is not None:
                self._thread.join(timeout=0.5)
            self._thread = None
            return self.get_status()

    def step(self) -> dict[str, Any]:
        with self.lock:
            self.running = False
            self.simulation.tick()
            return self.get_status()

    def reset(self) -> dict[str, Any]:
        with self.lock:
            self.running = False
            self.world = self._build_world()
            self.simulation = Simulation(self.world)
            self.observatory = Observatory()
            self.snapshots = []
            self.last_snapshot = None
            return self.get_status()

    def get_status(self) -> dict[str, Any]:
        with self.lock:
            world = self.world
            return {
                "running": self.running,
                "day": getattr(world.clock, "day", 1),
                "hour": getattr(world.clock, "hour", 0),
                "experiment_id": self.experiment_id,
                "population": len(getattr(world, "npcs", [])),
                "event_count": len(getattr(getattr(world, "event_log", None), "events", [])),
                "intervention_count": len(getattr(world, "intervention_history", [])),
                "resource_food": getattr(world.resources.get("Food"), "quantity", 0),
                "environment": getattr(world.environment_system, "weather", "clear"),
                "world_name": world.metadata.get("era", "TinyWorld"),
            }

    def get_world(self) -> dict[str, Any]:
        with self.lock:
            return _safe_json(self.observatory.inspect_world(self.world))

    def get_npcs(self) -> list[dict[str, Any]]:
        with self.lock:
            items = []
            for npc in self.world.npcs:
                snapshot = self.observatory.inspect_npc(self.world, npc.name)
                items.append(_safe_json(snapshot))
            return items

    def get_npc(self, npc_id: str) -> dict[str, Any]:
        with self.lock:
            try:
                return _safe_json(self.observatory.inspect_npc(self.world, npc_id))
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    def get_events(self) -> list[dict[str, Any]]:
        with self.lock:
            items = []
            for event in getattr(getattr(self.world, "event_log", None), "events", []):
                items.append(_safe_json(event))
            return items

    def get_interventions(self) -> list[dict[str, Any]]:
        with self.lock:
            return [_safe_json(item) for item in getattr(self.world, "intervention_history", [])]

    def get_communications(self) -> list[dict[str, Any]]:
        with self.lock:
            messages: list[dict[str, Any]] = []
            for npc in getattr(self.world, "npcs", []):
                for message in getattr(npc, "communication_memory", []):
                    messages.append(
                        {
                            "sender": getattr(message, "sender", "unknown"),
                            "receiver": getattr(message, "receiver", npc.name),
                            "content": getattr(message, "content", ""),
                            "message_type": getattr(message, "message_type", "tell").value
                            if hasattr(getattr(message, "message_type", None), "value")
                            else str(getattr(message, "message_type", "tell")),
                            "timestamp": getattr(message, "timestamp", None),
                            "claims": jsonable_encoder(getattr(message, "claims", {})),
                            "source": getattr(message, "source_reliability", None),
                            "origin": "communication",
                        }
                    )
            if not messages:
                for event in getattr(getattr(self.world, "event_log", None), "events", []):
                    if getattr(event, "event_type", "") == "communication":
                        messages.append(
                            {
                                "sender": getattr(event, "actor", "unknown"),
                                "receiver": getattr(event, "target", "unknown"),
                                "content": getattr(event, "description", ""),
                                "message_type": "tell",
                                "timestamp": (getattr(event, "day", 1), getattr(event, "hour", 0)),
                                "claims": jsonable_encoder(getattr(event, "properties", {})),
                                "source": None,
                                "origin": "event",
                            }
                        )
            return messages

    def get_beliefs(self) -> list[dict[str, Any]]:
        with self.lock:
            beliefs = []
            for npc in getattr(self.world, "npcs", []):
                for belief in getattr(npc, "beliefs", []):
                    beliefs.append(
                        {
                            "npc": npc.name,
                            "subject": str(getattr(belief, "subject", "")),
                            "predicate": str(getattr(belief, "predicate", "")),
                            "value": getattr(belief, "value", None),
                            "confidence": getattr(belief, "confidence", 0.0),
                            "source": getattr(belief, "source", None),
                            "origin_type": getattr(belief, "origin_type", None),
                        }
                    )
            return beliefs

    def get_truth_vs_belief(self) -> list[dict[str, Any]]:
        with self.lock:
            items = []
            for comparison in self.observatory.compare_beliefs(self.world):
                items.append(
                    {
                        "npc_name": comparison.npc_name,
                        "subject": comparison.subject,
                        "predicate": comparison.predicate,
                        "world_value": comparison.world_value,
                        "npc_value": comparison.npc_value,
                        "source": comparison.source,
                        "known": comparison.known,
                        "correct": comparison.world_value == comparison.npc_value if comparison.known and comparison.npc_value is not None else None,
                        "status": "unknown" if not comparison.known else ("correct" if comparison.world_value == comparison.npc_value else "false"),
                    }
                )
            return items

    def get_metrics(self) -> dict[str, Any]:
        with self.lock:
            metrics = self.observatory.metrics(self.world)
            return _safe_json(metrics.as_dict())

    def add_snapshot(self) -> dict[str, Any]:
        with self.lock:
            snapshot = _safe_json(self.observatory.inspect_world(self.world))
            snapshot["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.snapshots.append(snapshot)
            self.last_snapshot = snapshot
            return snapshot

    def get_snapshots(self) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.snapshots)

    def save_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        with self.lock:
            checkpoint = self.observatory.save_checkpoint(self.world, checkpoint_id, path=str(CHECKPOINT_DIR / f"{checkpoint_id}.json"))
            self.checkpoint_store[checkpoint_id] = str(CHECKPOINT_DIR / f"{checkpoint_id}.json")
            payload = _safe_json(checkpoint.to_dict())
            return payload

    def load_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        with self.lock:
            path = self.checkpoint_store.get(checkpoint_id) or str(CHECKPOINT_DIR / f"{checkpoint_id}.json")
            checkpoint_path = Path(path)
            if not checkpoint_path.exists():
                raise FileNotFoundError(f"Checkpoint {checkpoint_id} not found")
            checkpoint = self.observatory.load_checkpoint(checkpoint_path)
            self.running = False
            self.world = self._restore_world(checkpoint)
            self.simulation = Simulation(self.world)
            self.observatory = Observatory()
            return _safe_json(checkpoint.to_dict())

    def _restore_world(self, checkpoint: Any) -> World:
        world = World(seed=int(getattr(checkpoint, "seed", 42)))
        checkpoint_state = checkpoint.to_dict()
        world_state = checkpoint_state.get("world_state", {})
        metadata = world_state.get("metadata", {})
        if isinstance(metadata, dict):
            world.metadata = dict(metadata)
        resources = world_state.get("resources", {})
        world.resources = {}
        for key, value in resources.items():
            if isinstance(value, dict):
                quantity = int(value.get("quantity", 0))
            else:
                quantity = int(value)
            world.resources[key] = Resource(name=key, quantity=quantity)
        world.food = world.resources.get("Food", Resource(name="Food", quantity=0))
        for building_name in world_state.get("buildings", []):
            world.add_building(Building(name=str(building_name), building_type="generic"))
        world.npcs = []
        for npc_data in checkpoint_state.get("npc_state", []):
            npc = NPC(
                name=str(npc_data.get("name", "NPC")),
                role=str(npc_data.get("role", "villager")),
                money=int(npc_data.get("money", 0)),
                home=str(npc_data.get("home", "Settlement")),
                location=str(npc_data.get("location", "Settlement")),
                food=int(npc_data.get("food", 0)),
                energy=int(npc_data.get("energy", 100)),
                hunger=int(npc_data.get("hunger", 0)),
            )
            npc.beliefs = []
            npc.memories = []
            npc.communication_memory = []
            npc.relationships = {}
            world.add_npc(npc)
        world.event_log = type("EventLog", (), {"events": []})()
        for event in checkpoint_state.get("event_state", []):
            world.event_log.events.append(
                WorldEvent(
                    day=int(event.get("day", 1) if isinstance(event, dict) else 1),
                    hour=int(event.get("hour", 0) if isinstance(event, dict) else 0),
                    event_type=str(event.get("event_type", "system")),
                    actor=str(event.get("actor", "system")),
                    target=str(event.get("target", "world")),
                    description=str(event.get("description", "")),
                    properties=dict(event.get("properties", {})),
                    consequences=(),
                    sequence=int(event.get("sequence", 0)),
                    cause=str(event.get("cause", "checkpoint")),
                )
            )
        world.intervention_history = list(checkpoint_state.get("intervention_history", []))
        return world


APP_STATE = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="TinyWorld God Observatory", lifespan=lifespan)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return APP_STATE.get_status()


@app.get("/api/world")
async def world_payload() -> dict[str, Any]:
    return APP_STATE.get_world()


@app.get("/api/npcs")
async def npcs() -> list[dict[str, Any]]:
    return APP_STATE.get_npcs()


@app.get("/api/npcs/{npc_id}")
async def npc_detail(npc_id: str) -> dict[str, Any]:
    return APP_STATE.get_npc(npc_id)


@app.get("/api/events")
async def events() -> list[dict[str, Any]]:
    return APP_STATE.get_events()


@app.get("/api/interventions")
async def interventions() -> list[dict[str, Any]]:
    return APP_STATE.get_interventions()


@app.get("/api/communications")
async def communications() -> list[dict[str, Any]]:
    return APP_STATE.get_communications()


@app.get("/api/beliefs")
async def beliefs() -> list[dict[str, Any]]:
    return APP_STATE.get_beliefs()


@app.get("/api/truth-vs-belief")
async def truth_vs_belief() -> list[dict[str, Any]]:
    return APP_STATE.get_truth_vs_belief()


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    return APP_STATE.get_metrics()


@app.get("/api/snapshots")
async def snapshots() -> list[dict[str, Any]]:
    return APP_STATE.get_snapshots()


@app.get("/api/checkpoints")
async def checkpoints() -> dict[str, Any]:
    return {"checkpoints": sorted(APP_STATE.checkpoint_store.keys())}


@app.post("/api/simulation/start")
async def start_simulation() -> dict[str, Any]:
    try:
        return APP_STATE.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/simulation/pause")
async def pause_simulation() -> dict[str, Any]:
    return APP_STATE.pause()


@app.post("/api/simulation/step")
async def step_simulation() -> dict[str, Any]:
    return APP_STATE.step()


@app.post("/api/simulation/reset")
async def reset_simulation() -> dict[str, Any]:
    return APP_STATE.reset()


@app.post("/api/interventions")
async def apply_intervention(request: InterventionRequest) -> dict[str, Any]:
    try:
        intervention = GodIntervention(
            operation=request.operation,
            target=request.target,
            properties=request.properties,
            value=request.value,
            visibility=request.visibility,
        )
        result = APP_STATE.world.intervention_engine.apply(APP_STATE.world, intervention)
        return {
            "success": bool(result.success),
            "message": result.message,
            "operation": result.operation.value,
            "target": result.target,
            "changed": bool(result.changed),
        }
    except (TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/snapshots")
async def capture_snapshot() -> dict[str, Any]:
    return APP_STATE.add_snapshot()


@app.post("/api/checkpoints/save")
async def save_checkpoint(request: CheckpointRequest) -> dict[str, Any]:
    checkpoint_id = request.checkpoint_id.strip()
    if not checkpoint_id:
        raise HTTPException(status_code=400, detail="Checkpoint ID is required.")
    return APP_STATE.save_checkpoint(checkpoint_id)


@app.post("/api/checkpoints/load")
async def load_checkpoint(request: CheckpointRequest) -> dict[str, Any]:
    checkpoint_id = request.checkpoint_id.strip()
    if not checkpoint_id:
        raise HTTPException(status_code=400, detail="Checkpoint ID is required.")
    try:
        payload = APP_STATE.load_checkpoint(checkpoint_id)
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("WORLD.app:app", host="127.0.0.1", port=8000, reload=False)
