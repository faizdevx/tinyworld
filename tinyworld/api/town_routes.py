"""HTTP and WebSocket routes for the Town: the living world seen from above.

A *runtime* wraps one branch: its asynchronous residents, the town's own additions (fortune,
petitions, the paper), the creators, a podium desk and the pantheon. Opening a branch in the
Town view lays it out on a tile map if it has none. Only one thing may write to a branch at a
time, so a branch played in the Town view should not also be played from the older view.

Messages on the socket (protocol v1 additions):

- ``snapshot``     everything needed to draw: time, chunks, places, people, petitions, papers
- ``chunk.upsert`` one chunk, when the map grows
- ``position``     all people's tiles, batched once per step
- ``petition``     a petition opened or closed (the decision itself rides the studio queue)
- ``edition.add``  a new paper
"""

import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from tinyworld.core.entropy import Entropy
from tinyworld.eval import multiverse
from tinyworld.genesis import layout
from tinyworld.llm.types import CallContext
from tinyworld.sim import newspaper, watch
from tinyworld.sim.budget import Budget
from tinyworld.sim.clock import AsyncSimulation
from tinyworld.sim.cost import DailyBudget
from tinyworld.sim.loop import Simulation
from tinyworld.sim.town import Town
from tinyworld.studio.creators import Creators, ModelCartographer, ScriptedCartographer
from tinyworld.studio.desk import PetitionDesk
from tinyworld.world import frontier, gods, grid, petitions, walking

STEP_MINUTES = 10


class RunRequest(BaseModel):
    minutes: int = 60


class InterviewRequest(BaseModel):
    person: str
    question: str
    appear: bool = False


class AnswerRequest(BaseModel):
    power: str
    text: str = ""
    command: str = ""


class MultiverseRequest(BaseModel):
    runs: int = 5
    hours: int = 24
    concurrency: int = 2


class GodRequest(BaseModel):
    id: str
    name: str
    role: str = "observer"
    points: int | None = None
    ai: bool = False
    goal: str = ""


class CommandRequest(BaseModel):
    god: str
    text: str


def chunk_json(state, key: str) -> dict:
    chunk = state.grid[key]
    cx, cy = frontier.parse(key)
    return {
        "key": key, "cx": cx, "cy": cy, "terrain": chunk.terrain,
        "regions": [r.model_dump() for r in chunk.regions],
    }


def person_state(state, person, last) -> str:
    if walking.route_of(person):
        return "walking"
    text = (last.narration if last else "").lower()
    if "prays" in text or person.location in petitions.holy_places(state) and any(p.by == person.id for p in petitions.open_petitions(state)):
        return "praying"
    if "sleeps" in text:
        return "sleeping"
    if last is not None and last.kind == "utterance":
        return "talking"
    return "idle"


class TownRuntime:
    def __init__(self, hub, studios, branch_id: str) -> None:
        self.hub = hub
        self.branch_id = branch_id
        self.session = hub.session(branch_id)
        llm = hub.llm_for(self.session)
        digest = hub.world_digest(self.session.world_id)
        self.budget = DailyBudget(self.session.store, branch_id)
        self.sim = Simulation(self.session, llm, embedder=hub.embedder, world_digest=digest, budget=self.budget)
        self.entropy = Entropy(self.session.store, branch_id, seq=lambda: self.session.state.seq)
        self.clocks = AsyncSimulation(self.sim, self.entropy)
        cartographer = ModelCartographer(llm, digest) if llm is not None and hub.llm is not None else ScriptedCartographer()
        self.studio = None
        self.desk = None
        try:
            self.studio = studios.foreman(self.session.world_id).studio
        except Exception:  # noqa: BLE001 - the town works without a podium
            self.studio = None
        self.creators = Creators(cartographer, studio=self.studio)
        self.town = Town(
            self.sim, self.entropy, clocks=self.clocks, creators=self.creators, drives_on=True, chaos=None,
            god=None,
        )
        if self.studio is not None:
            self.desk = PetitionDesk(self.studio, self.town)
            self.town.desk = self.desk
        self.pantheon = gods.Pantheon(self.session.store, self.session.world_id)
        self.subscribers: set[asyncio.Queue] = set()
        self.running = False
        self._task: asyncio.Task | None = None
        self._known_chunks: set[str] = set(self.session.state.grid)
        self._papers: set[str] = set()
        self.lock = asyncio.Lock()
        if not self.session.state.grid:
            self.town.commit(layout.layout(self.session.state))
            self._known_chunks = set(self.session.state.grid)

    # -- what the page draws ----------------------------------------------

    def people(self) -> list[dict]:
        state = self.session.state
        store = self.session.store
        out = []
        for p in sorted(state.people(), key=lambda p: p.id):
            at = grid.position_of(p)
            last = store.events(self.branch_id, actor=p.id, limit=1, newest_first=True)
            out.append({
                "id": p.id, "name": p.name, "x": at[0] if at else None, "y": at[1] if at else None,
                "place": state.entities[p.location].name if p.location in state.entities else "",
                "state": person_state(state, p, last[0] if last else None),
                "doing": last[0].narration if last else "", "faith": petitions.faith_of(p),
                "tier": p.attrs.get("tier", 0), "child": p.attrs.get("status") == "child",
            })
        return out

    def petition_list(self) -> list[dict]:
        state = self.session.state
        return [
            {"id": p.id, "by": p.by, "name": state.entities[p.by].name, "kind": p.kind, "text": p.text,
             "offering": p.offering, "place": p.place}
            for p in petitions.open_petitions(state)
        ]

    def papers(self) -> list[dict]:
        return [
            {"day": day, "headline": e.headline}
            for day, e in sorted(self.town.editions.items(), reverse=True)
        ]

    def snapshot(self) -> dict:
        state = self.session.state
        return {
            "type": "snapshot", "v": 1, "branch_id": self.branch_id, "world_id": self.session.world_id,
            "time": state.sim_time.isoformat(), "running": self.running, "seq": state.seq,
            "chunks": [chunk_json(state, k) for k in sorted(state.grid)],
            "places": {
                e.id: {"name": e.name, "kind": e.attrs.get("place_type", "")}
                for e in state.entities.values() if e.kind == "place" and not e.id.startswith(("place:blk_", "place:wild_"))
            },
            "people": self.people(), "petitions": self.petition_list(), "papers": self.papers(),
            "holy": petitions.holy_places(state), "unexplored": sorted(frontier.missing_neighbours(state)),
            "pantheon": [d.model_dump() for d in self.pantheon.members.values()],
        }

    # -- running ------------------------------------------------------------

    def publish(self, message: dict) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                self.subscribers.discard(q)

    async def step(self, minutes: int = STEP_MINUTES) -> None:
        async with self.lock:
            await self.town.advance(minutes)
            state = self.session.state
            for key in sorted(set(state.grid) - self._known_chunks):
                self._known_chunks.add(key)
                self.publish({"type": "chunk.upsert", "chunk": chunk_json(state, key)})
            for day, edition in sorted(self.town.editions.items()):
                if day not in self._papers:
                    self._papers.add(day)
                    self.publish({"type": "edition.add", "day": day, "headline": edition.headline})
            self.publish({"type": "position", "time": state.sim_time.isoformat(), "seq": state.seq, "people": self.people()})
            self.publish({"type": "petition", "open": self.petition_list()})

    async def advance(self, minutes: int) -> None:
        done = 0
        while done < minutes:
            await self.step(min(STEP_MINUTES, minutes - done))
            done += STEP_MINUTES

    def play(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.running = True

        async def loop() -> None:
            try:
                while self.running:
                    await self.step()
                    await asyncio.sleep(0.05)
            finally:
                self.running = False

        self._task = asyncio.create_task(loop())

    def pause(self) -> None:
        self.running = False


def install(app: FastAPI, the_hub) -> None:
    towns: dict[str, TownRuntime] = {}
    jobs: dict[str, dict] = {}
    app.state.towns = towns

    def runtime(branch_id: str) -> TownRuntime:
        if branch_id not in towns:
            try:
                towns[branch_id] = TownRuntime(the_hub(), app.state.studios, branch_id)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=404, detail=f"cannot open {branch_id}: {exc}") from exc
        return towns[branch_id]

    @app.get("/api/town/{branch_id}")
    async def town_snapshot(branch_id: str) -> dict:
        return runtime(branch_id).snapshot()

    @app.get("/api/town/{branch_id}/chunk/{cx}/{cy}")
    async def town_chunk(branch_id: str, cx: int, cy: int) -> dict:
        state = runtime(branch_id).session.state
        key = frontier.chunk_key(cx, cy)
        if key not in state.grid:
            raise HTTPException(status_code=404, detail="that ground has not been made yet")
        return chunk_json(state, key)

    @app.post("/api/town/{branch_id}/run")
    async def town_run(branch_id: str, request: RunRequest) -> dict:
        r = runtime(branch_id)
        await r.advance(max(1, min(request.minutes, 24 * 60)))
        return {"time": r.session.state.sim_time.isoformat(), "seq": r.session.state.seq}

    @app.post("/api/town/{branch_id}/play")
    async def town_play(branch_id: str) -> dict:
        runtime(branch_id).play()
        return {"running": True}

    @app.post("/api/town/{branch_id}/pause")
    async def town_pause(branch_id: str) -> dict:
        runtime(branch_id).pause()
        return {"running": False}

    @app.get("/api/town/{branch_id}/people")
    async def town_people(branch_id: str) -> list[dict]:
        return runtime(branch_id).people()

    @app.get("/api/town/{branch_id}/follow/{person_id}")
    async def town_follow(branch_id: str, person_id: str) -> dict:
        r = runtime(branch_id)
        if person_id not in r.session.state.entities:
            raise HTTPException(status_code=404, detail="no such person")
        return watch.follow(r.sim, person_id)

    @app.post("/api/town/{branch_id}/interview")
    async def town_interview(branch_id: str, request: InterviewRequest) -> dict:
        r = runtime(branch_id)
        if request.person not in r.session.state.entities:
            raise HTTPException(status_code=404, detail="no such person")
        async with r.lock:
            text = await watch.interview(r.sim, request.person, request.question, appear=request.appear)
        return {"answer": text, "appeared": request.appear}

    @app.get("/api/town/{branch_id}/papers")
    async def town_papers(branch_id: str) -> list[dict]:
        r = runtime(branch_id)
        return [
            {"day": d, "headline": e.headline, "text": e.text(), "stories": [s.model_dump() for s in e.stories], "rumours": e.rumours}
            for d, e in sorted(r.town.editions.items(), reverse=True)
        ]

    @app.get("/api/town/{branch_id}/graph/{kind}")
    async def town_graph(branch_id: str, kind: str) -> dict:
        r = runtime(branch_id)
        if kind == "relationships":
            return watch.relationship_graph(r.session.state)
        if kind == "rumours":
            return watch.rumour_graph(r.session.store, branch_id)
        raise HTTPException(status_code=404, detail="relationships or rumours")

    @app.get("/api/town/{branch_id}/why/{seq}")
    async def town_why(branch_id: str, seq: int) -> dict:
        return watch.why(runtime(branch_id).session.store, branch_id, seq)

    @app.get("/api/town/{branch_id}/timeline")
    async def town_timeline(branch_id: str, start: str, end: str, step: int = 30) -> list[dict]:
        r = runtime(branch_id)
        try:
            a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="start and end are ISO times") from exc
        if (b - a).total_seconds() / 60 / max(step, 1) > 2000:
            raise HTTPException(status_code=422, detail="too many frames; widen the step")
        return watch.frames(r.session.store, branch_id, a, b, max(step, 1))

    @app.get("/api/town/{branch_id}/petitions")
    async def town_petitions(branch_id: str) -> list[dict]:
        return runtime(branch_id).petition_list()

    @app.post("/api/town/{branch_id}/petitions/{petition_id}/answer")
    async def town_answer(branch_id: str, petition_id: str, request: AnswerRequest) -> dict:
        r = runtime(branch_id)
        if request.power not in petitions.ANSWERS:
            raise HTTPException(status_code=422, detail=f"power is one of {', '.join(petitions.ANSWERS)}")
        async with r.lock:
            events = await r.town.answer(petition_id, request.power, request.text, command=request.command)
        if not events:
            raise HTTPException(status_code=409, detail=r.town.last_refused or "no open petition by that id")
        r.publish({"type": "petition", "open": r.petition_list()})
        return {"answered": True, "faith_refused": False}

    @app.get("/api/town/{branch_id}/gods")
    async def town_gods(branch_id: str) -> list[dict]:
        return [d.model_dump() for d in runtime(branch_id).pantheon.members.values()]

    @app.post("/api/town/{branch_id}/gods")
    async def town_add_god(branch_id: str, request: GodRequest) -> dict:
        try:
            d = runtime(branch_id).pantheon.add(request.id, request.name, request.role, points=request.points, ai=request.ai, goal=request.goal)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return d.model_dump()

    @app.post("/api/town/{branch_id}/gods/command")
    async def town_god_command(branch_id: str, request: CommandRequest) -> dict:
        r = runtime(branch_id)
        if request.god not in r.pantheon.members:
            raise HTTPException(status_code=404, detail="no such god")
        parser = r.town.channel.parser
        parsed = await parser.parse(r.session.state, request.text, CallContext(branch_id, r.session.state.seq)) if parser else None
        if parsed is None or not parsed.commands:
            raise HTTPException(status_code=422, detail=(parsed.question if parsed else "no model to read that") or "that could not be understood")
        act = gods.Act(request.god, "command", request.text, parsed.commands)
        async with r.lock:
            await gods.run_window(r.town, r.pantheon, [act], studio=r.studio)
        return {"result": act.result, "done": act.done}

    @app.post("/api/town/{branch_id}/multiverse")
    async def town_multiverse(branch_id: str, request: MultiverseRequest) -> dict:
        r = runtime(branch_id)
        job_id = f"mv{len(jobs) + 1}"
        jobs[job_id] = {"status": "running", "runs": request.runs, "hours": request.hours, "branches": []}

        async def advance(branch, index: int) -> None:
            hub = the_hub()
            sub = TownRuntime(hub, app.state.studios, branch.branch_id)
            await sub.advance(request.hours * 60)

        async def go() -> None:
            seq = r.session.state.seq
            try:
                runs = await multiverse.run(r.session, request.runs, advance, concurrency=request.concurrency)
                spread = multiverse.spread([x.session for x in runs], after=seq)
                jobs[job_id].update(
                    status="done", spread=spread.as_dict(),
                    branches=[{"index": x.index, "branch_id": x.session.branch_id, "error": x.error, "seconds": x.seconds} for x in runs],
                )
            except Exception as exc:  # noqa: BLE001
                jobs[job_id].update(status="error", error=repr(exc))

        asyncio.create_task(go())
        return {"job": job_id}

    @app.get("/api/town/multiverse/{job_id}")
    async def town_multiverse_result(job_id: str) -> dict:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="no such job")
        return jobs[job_id]

    @app.websocket("/ws/town/{branch_id}")
    async def town_socket(socket: WebSocket, branch_id: str) -> None:
        try:
            r = runtime(branch_id)
        except HTTPException:
            await socket.close(code=4404)
            return
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        r.subscribers.add(queue)
        await socket.accept()
        try:
            await socket.send_text(json.dumps(r.snapshot()))
            closed = asyncio.create_task(socket.receive())
            while True:
                message = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({closed, message}, return_when=asyncio.FIRST_COMPLETED)
                if closed in done:
                    message.cancel()
                    break
                await socket.send_text(json.dumps(message.result()))
        except WebSocketDisconnect:
            pass
        finally:
            r.subscribers.discard(queue)
