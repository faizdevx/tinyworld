"""HTTP and WebSocket API. ``python -m tinyworld.api.app`` serves it on port 8000."""

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from tinyworld.api import views
from tinyworld.api.hub import Hub
from tinyworld.api.runner import event_json
from tinyworld.core import branches
from tinyworld.core.causes import cause_graph
from tinyworld.core.events import Intent
from tinyworld.core.store import Store, StoreError
from tinyworld.core.time import parse_step
from tinyworld.llm.types import LLMFatal
from tinyworld.eval import anachronism, invariants, judge
from tinyworld.eval.metrics import world_metrics
from tinyworld.sim.replay import replay
from tinyworld.fixtures import toy
from tinyworld.god.channel import GodResult
from tinyworld.sim.step import apply_intents

STATIC = Path(__file__).parent / "static"


class IntentsRequest(BaseModel):
    intents: list[Intent]


class ConnectRequest(BaseModel):
    provider: str
    key: str = ""
    base_url: str | None = None


class WorldRequest(BaseModel):
    premise: str


class AnswerRequest(BaseModel):
    text: str


class StageRequest(BaseModel):
    stage: str


class SeedRequest(BaseModel):
    name: str = "main"


class ForkRequest(BaseModel):
    at_seq: int | None = None
    name: str = "what-if"


class RunRequest(BaseModel):
    action: str
    delay: float | None = None


class SkipRequest(BaseModel):
    span: str | None = None
    minutes: int | None = None


class BudgetRequest(BaseModel):
    run_cap: float | None = None
    agent_cap: float | None = None
    add: float = 0.0


class GodRequest(BaseModel):
    text: str


def create_app(hub: Hub | None = None) -> FastAPI:
    app = FastAPI(title="TinyWorld")
    app.state.hub = hub or Hub()

    @app.exception_handler(LLMFatal)
    async def model_unavailable(request, exc: LLMFatal):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    def the_hub() -> Hub:
        return app.state.hub

    def runner_for(branch_id: str):
        try:
            return the_hub().runner(branch_id)
        except StoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def world_or_404(world_id: str):
        try:
            return the_hub().store.world(world_id)
        except StoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def branch_json(info: branches.BranchInfo) -> dict:
        return {
            "id": info.id, "world_id": info.world_id, "parent_id": info.parent_id,
            "fork_seq": info.fork_seq, "name": info.name, "head_seq": info.head_seq,
        }

    # -- pages ----------------------------------------------------------

    @app.get("/")
    async def index() -> RedirectResponse:
        return RedirectResponse("/app/")

    @app.get("/debug")
    async def debug_page() -> FileResponse:
        return FileResponse(STATIC / "debug.html")

    # -- worlds and genesis ---------------------------------------------

    @app.get("/api/status")
    async def status() -> dict:
        hub = the_hub()
        return {
            "model_configured": hub.has_model,
            "offline": hub.offline,
            "tiers": hub.config.tiers,
        }

    @app.post("/api/connect")
    async def connect(request: ConnectRequest) -> dict:
        """Use a model key from now on. Held in memory only, never written."""
        hub = the_hub()
        try:
            await hub.connect(request.provider, request.key, request.base_url)
            app.state.studios.reset()
        except LLMFatal as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"model_configured": True, "offline": False, "tiers": hub.config.tiers}

    @app.get("/api/worlds")
    async def worlds() -> list[dict]:
        hub = the_hub()
        return [
            {
                "id": row["id"],
                "premise": row["premise"],
                "created_at": row["created_at"],
                "stage": hub.genesis_job(row["id"]).stage,
                "branches": len(hub.store.branches(row["id"])),
            }
            for row in hub.store.worlds()
        ]

    @app.post("/api/worlds")
    async def create_world(request: WorldRequest) -> dict:
        hub = the_hub()
        premise = request.premise.strip()
        if not premise:
            raise HTTPException(status_code=422, detail="A premise is needed.")
        try:
            world_id = hub.pipeline().create_world(premise)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        hub.start_genesis(world_id)
        return {"world_id": world_id}

    @app.post("/api/worlds/toy")
    async def create_toy() -> dict:
        hub = the_hub()
        session = hub.adopt(toy.build_toy(hub.store))
        hub.genesis_job(session.world_id).stage = "done"
        return {"world_id": session.world_id, "branch_id": session.branch_id}

    @app.get("/api/worlds/{world_id}")
    async def world(world_id: str) -> dict:
        row = world_or_404(world_id)
        hub = the_hub()
        return {
            "id": row["id"],
            "premise": row["premise"],
            "bible_version": row["bible_version"],
            "genesis": hub.genesis_job(world_id).view(),
            "branches": [branch_json(b) for b in branches.tree(hub.store, world_id)],
            "offline": hub.store.meta_get(world_id, "canned_genesis") == "1",
            "prepared": hub.prepared_of(world_id),
        }

    @app.post("/api/worlds/{world_id}/genesis/answer")
    async def answer(world_id: str, request: AnswerRequest) -> dict:
        row = world_or_404(world_id)
        hub = the_hub()
        if hub.genesis_job(world_id).running:
            raise HTTPException(status_code=409, detail="Genesis is still running.")
        hub.store.execute(
            "UPDATE worlds SET premise=? WHERE id=?",
            (f"{row['premise']}\n{request.text.strip()}", world_id),
        )
        return hub.start_genesis(world_id).view()

    @app.post("/api/worlds/{world_id}/genesis/stage")
    async def rerun_stage(world_id: str, request: StageRequest) -> dict:
        world_or_404(world_id)
        hub = the_hub()
        if hub.genesis_job(world_id).running:
            raise HTTPException(status_code=409, detail="Genesis is still running.")
        return hub.start_genesis(world_id, request.stage).view()

    @app.get("/api/worlds/{world_id}/bible")
    async def bible(world_id: str, version: int | None = None) -> dict:
        world_or_404(world_id)
        hub = the_hub()
        return {
            "version": hub.bibles.version(world_id) if version is None else version,
            "bible": hub.bibles.load(world_id, version).model_dump(mode="json"),
        }

    @app.put("/api/worlds/{world_id}/bible/{section}")
    async def edit_bible(world_id: str, section: str, content: dict[str, Any]) -> dict:
        world_or_404(world_id)
        hub = the_hub()
        try:
            findings = hub.pipeline().edit(world_id, section, content)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_input=False)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        hub.genesis_job(world_id).findings = hub.bibles.load(world_id).critique.findings
        return {
            "version": hub.bibles.version(world_id),
            "findings": [f.model_dump() for f in findings],
        }

    @app.get("/api/worlds/{world_id}/sources")
    async def sources(world_id: str) -> list[dict]:
        world_or_404(world_id)
        hub = the_hub()
        from tinyworld.genesis.research import Researcher

        found = Researcher(hub.store, hub.genesis_llm(), hub.search).sources(world_id)
        return [
            {"id": s.id, "url": s.url, "title": s.title, "notes": [n.claim for n in s.notes]}
            for s in found
        ]

    @app.post("/api/worlds/{world_id}/seed")
    async def seed(world_id: str, request: SeedRequest) -> dict:
        world_or_404(world_id)
        hub = the_hub()
        try:
            session, notes = hub.pipeline().seed(world_id, request.name)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        hub.adopt(session)
        return {"branch_id": session.branch_id, "notes": [n.model_dump() for n in notes]}

    # -- branches -------------------------------------------------------

    @app.get("/api/branches/{branch_id}")
    async def branch(branch_id: str) -> dict:
        runner = runner_for(branch_id)
        hub = the_hub()
        info = branches.info(hub.store, branch_id)
        return {**branch_json(info), "status": runner.status()}

    @app.post("/api/branches/{branch_id}/fork")
    async def fork(branch_id: str, request: ForkRequest) -> dict:
        runner = runner_for(branch_id)
        at_seq = runner.session.state.seq if request.at_seq is None else request.at_seq
        try:
            async with runner.lock:
                child = runner.session.fork(at_seq, request.name.strip() or "what-if")
        except StoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        the_hub().adopt(child)
        return {"branch_id": child.branch_id, "fork_seq": at_seq}

    @app.get("/api/branches/{branch_id}/state")
    async def state(branch_id: str, seq: int | None = None) -> dict:
        runner = runner_for(branch_id)
        if seq is None:
            return runner.session.state.model_dump(mode="json")
        try:
            return the_hub().store.state_at(branch_id, seq).model_dump(mode="json")
        except StoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/branches/{branch_id}/events")
    async def events(
        branch_id: str,
        after: int = 0,
        limit: int = 200,
        actor: str | None = None,
        kind: str | None = None,
        newest: bool = False,
    ) -> list[dict]:
        runner_for(branch_id)
        found = the_hub().store.events(
            branch_id, after=after, limit=min(limit, 1000), actor=actor, kind=kind,
            newest_first=newest,
        )
        return [event_json(event) for event in found]

    @app.post("/api/branches/{branch_id}/intents")
    async def intents(branch_id: str, request: IntentsRequest) -> dict:
        runner = runner_for(branch_id)
        async with runner.lock:
            the_hub().store.journal_add(
                branch_id, runner.session.state.seq, "intents",
                {"intents": [i.model_dump(mode="json") for i in request.intents]},
            )
            result = await apply_intents(
                runner.session, the_hub().game_master(branch_id), request.intents
            )
        return {
            "outcomes": [o.model_dump(mode="json") for o in result.outcomes],
            "events": [event_json(e) for e in result.events],
            "observations": [o.model_dump(mode="json") for o in result.observations],
        }

    @app.post("/api/branches/{branch_id}/run")
    async def run(branch_id: str, request: RunRequest) -> dict:
        runner = runner_for(branch_id)
        if request.action == "play":
            runner.play(request.delay)
        elif request.action == "pause":
            await runner.pause()
        elif request.action == "step":
            await runner.pause()
            result = await runner.step()
            return {
                "status": runner.status(),
                "paused": result.paused,
                "events": [event_json(e) for e in result.events],
            }
        else:
            raise HTTPException(status_code=422, detail="action must be play, pause or step")
        return {"status": runner.status()}

    @app.post("/api/branches/{branch_id}/skip")
    async def skip(branch_id: str, request: SkipRequest) -> dict:
        runner = runner_for(branch_id)
        try:
            minutes = request.minutes if request.minutes else parse_step(request.span or "")
            if minutes <= 0:
                raise ValueError("a skip must move time forward")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = await runner.skip(minutes)
        return {
            "status": runner.status(),
            "complete": result.complete,
            "stopped": result.stopped,
            "periods": result.periods,
            "summaries": result.summaries,
            "rejected": [{"narration": n, "reason": r} for n, r in result.rejected],
            "events": len(result.events),
        }

    @app.post("/api/branches/{branch_id}/budget")
    async def budget(branch_id: str, request: BudgetRequest) -> dict:
        runner = runner_for(branch_id)
        runner.set_budget(request.run_cap, request.agent_cap, request.add)
        return {"status": runner.status()}

    @app.post("/api/branches/{branch_id}/god")
    async def god(branch_id: str, request: GodRequest) -> dict:
        runner = runner_for(branch_id)
        if not request.text.strip():
            raise HTTPException(status_code=422, detail="Say something.")
        result = await runner.god_submit(request.text.strip())
        return result.model_dump(mode="json")

    @app.post("/api/branches/{branch_id}/god/fork")
    async def god_fork(branch_id: str, result: GodResult) -> dict:
        """Confirm a ``needs_fork`` verdict: branch at that moment and apply there."""
        runner = runner_for(branch_id)
        try:
            async with runner.lock:
                child, applied = await runner.god.apply_in_fork(runner.session, result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        the_hub().adopt(child)
        return {"branch_id": child.branch_id, "result": applied.model_dump(mode="json")}

    # -- inspection -----------------------------------------------------

    @app.get("/api/branches/{branch_id}/people")
    async def people(branch_id: str) -> list[dict]:
        return views.people_view(runner_for(branch_id).session.state)

    @app.get("/api/branches/{branch_id}/agents/{agent_id}")
    async def agent(branch_id: str, agent_id: str) -> dict:
        view = views.agent_view(runner_for(branch_id), agent_id)
        if view is None:
            raise HTTPException(status_code=404, detail=f"no person {agent_id}")
        return view

    @app.get("/api/branches/{branch_id}/causes/{seq}")
    async def causes(branch_id: str, seq: int) -> dict:
        runner_for(branch_id)
        return cause_graph(the_hub().store, branch_id, seq)

    @app.get("/api/branches/{branch_id}/chronicle")
    async def chronicle(branch_id: str) -> list[dict]:
        runner_for(branch_id)
        return views.chronicle_view(the_hub().store, branch_id)

    @app.get("/api/branches/{branch_id}/metrics")
    async def metrics(branch_id: str) -> dict:
        runner = runner_for(branch_id)
        return world_metrics(the_hub().store, branch_id, runner.session.state)

    @app.get("/api/branches/{branch_id}/checks")
    async def checks(branch_id: str) -> dict:
        """Invariant violations and anachronisms in this branch's log."""
        runner = runner_for(branch_id)
        store = the_hub().store
        found = anachronism.scan(store, branch_id, runner.session.state)
        return {
            "invariants": [str(v) for v in invariants.check_log(store, branch_id)],
            "anachronisms": [
                {"seq": a.seq, "term": a.term, "where": a.where, "text": a.text, "by_god": a.by_god}
                for a in found
            ],
            "leaks": len(anachronism.leaks(found)),
        }

    @app.post("/api/branches/{branch_id}/replay")
    async def verify_replay(branch_id: str) -> dict:
        """Re-run this branch from its recording on a new branch and compare."""
        runner = runner_for(branch_id)
        await runner.pause()
        async with runner.lock:
            report = await replay(the_hub().store, branch_id, the_hub().config)
        return report.as_dict()

    @app.post("/api/branches/{branch_id}/judge")
    async def judge_branch(branch_id: str) -> dict:
        """Persona-consistency scores for a sample of agents. Needs a real model."""
        runner = runner_for(branch_id)
        hub = the_hub()
        if hub.llm is None:
            raise HTTPException(status_code=503, detail="Judging needs a configured model.")
        results = await judge.judge_agents(
            hub.llm, hub.store, branch_id, runner.session.state
        )
        return {
            "summary": judge.summary(results),
            "agents": [
                {
                    "agent": r.agent, "name": r.name, "samples": r.samples,
                    "verdict": r.verdict.model_dump() if r.verdict else None,
                }
                for r in results
            ],
        }

    @app.get("/api/branches/{branch_id}/diff/{other_id}")
    async def diff(branch_id: str, other_id: str) -> dict:
        runner_for(branch_id)
        runner_for(other_id)
        return views.diff_view(the_hub().store, branch_id, other_id)

    @app.get("/api/branches/{branch_id}/export")
    async def export(branch_id: str) -> dict:
        runner = runner_for(branch_id)
        hub = the_hub()
        bible = hub.bibles.load(runner.session.world_id).model_dump(mode="json")
        return views.export_view(hub.store, branch_id, bible)

    # -- the studio: a team that builds a world --------------------------

    from tinyworld.api import studio_routes

    studio_routes.install(app, the_hub)
    from tinyworld.api import town_routes

    town_routes.install(app, the_hub)

    # -- live updates ---------------------------------------------------

    async def pump(socket: WebSocket, queue: asyncio.Queue, first: str) -> None:
        await socket.accept()
        await socket.send_text(first)
        # Watch the socket as well as the queue, so a closed tab is noticed
        # even while the simulation is idle.
        closed = asyncio.create_task(socket.receive())
        try:
            while True:
                message = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {message, closed}, return_when=asyncio.FIRST_COMPLETED
                )
                if closed in done:
                    received = closed.result()
                    if received.get("type") == "websocket.disconnect":
                        message.cancel()
                        break
                    closed = asyncio.create_task(socket.receive())
                if message in done:
                    await socket.send_text(message.result())
                else:
                    message.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            closed.cancel()

    @app.websocket("/ws/branches/{branch_id}")
    async def branch_socket(socket: WebSocket, branch_id: str) -> None:
        import json

        try:
            runner = the_hub().runner(branch_id)
        except StoreError:
            await socket.close(code=4404)
            return
        queue = runner.subscribe()
        try:
            await pump(socket, queue, json.dumps({"type": "status", "status": runner.status()}))
        finally:
            runner.unsubscribe(queue)

    @app.websocket("/ws/worlds/{world_id}")
    async def world_socket(socket: WebSocket, world_id: str) -> None:
        import json

        try:
            the_hub().store.world(world_id)
        except StoreError:
            await socket.close(code=4404)
            return
        job = the_hub().genesis_job(world_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        job.subscribers.add(queue)
        try:
            await pump(socket, queue, json.dumps({"type": "genesis", "genesis": job.view()}))
        finally:
            job.subscribers.discard(queue)

    if (STATIC / "app").exists():
        app.mount("/app", StaticFiles(directory=STATIC / "app", html=True), name="app")

    @app.middleware("http")
    async def revalidate_app_files(request, call_next):
        # The frontend is a set of ES modules: a browser holding some old and
        # some new ones breaks. Make it check each file on load (cheap, by ETag).
        response = await call_next(request)
        if request.url.path.startswith("/app"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def default_hub() -> Hub:
    """Worlds persist in ``TINYWORLD_DB`` (default: .tinyworld_data/worlds.sqlite)."""
    path = os.environ.get("TINYWORLD_DB", ".tinyworld_data/worlds.sqlite")
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return Hub(Store(path))


def serve() -> FastAPI:
    """Application factory: ``uvicorn tinyworld.api.app:serve --factory``."""
    return create_app(default_hub())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(serve(), host="127.0.0.1", port=8000)
