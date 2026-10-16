"""HTTP and WebSocket routes for the studio: the team that builds a world."""

import asyncio
import json
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from tinyworld.core.store import StoreError
from tinyworld.studio.replay import RecordingSearch
from tinyworld.studio.sim import ScriptedTeam, scripted_search
from tinyworld.studio.state import Studio
from tinyworld.studio.team import Foreman


def _sim_delay() -> float:
    """A pause per scripted step so a person can follow it. Tests set it to 0."""
    try:
        return float(os.environ.get("TINYWORLD_SIM_DELAY", "0.4"))
    except ValueError:
        return 0.4


class GoalRequest(BaseModel):
    goal: str
    # Hold every decision for the user (the default), or let the team decide.
    auto: bool = False
    # Dollars the goal may spend before the team stops and asks. None: no cap.
    budget: float | None = None


class AnswerRequest(BaseModel):
    option: str = ""
    text: str = ""


class ConsoleRequest(BaseModel):
    text: str


class MessageRequest(BaseModel):
    to: str
    text: str


class MemoryRequest(BaseModel):
    title: str
    body: str
    scope: str = "shared"


class BudgetRequest(BaseModel):
    amount: float


class MergeRequest(BaseModel):
    # Sections to merge now (default: all), and sections to send back with a note.
    merge: list[str] | None = None
    send_back: dict[str, str] = {}


class StudioHub:
    """Foremen by world, created on first use."""

    def __init__(self, hub) -> None:
        self.hub = hub
        self.foremen: dict[str, Foreman] = {}

    def foreman(self, world_id: str, *, auto: bool = False) -> Foreman:
        if world_id not in self.foremen:
            hub = self.hub
            try:
                hub.store.world(world_id)
            except StoreError as exc:
                raise KeyError(world_id) from exc
            studio = Studio(hub.store, world_id)
            goal = studio.data.goal.text if studio.data.goal else hub.store.world(world_id)["premise"]
            if hub.llm is not None:
                llm, search = hub.llm, hub.search
            else:
                # No model: the scripted team, so the studio still works end to end.
                from tinyworld.llm.structured import StructuredLLM

                llm = StructuredLLM(ScriptedTeam(delay=_sim_delay()), hub.config, hub.tracer)
                search = scripted_search(goal)
            # Every search and page is written down, so a build can be replayed.
            search = RecordingSearch(search, hub.store, world_id)
            foreman = Foreman(studio, llm, search, auto_answer=auto, max_parallel=3)
            self.foremen[world_id] = foreman
            # A build that was running when the server stopped carries on.
            unfinished = (
                studio.data.goal is not None
                and studio.data.goal.status in ("planning", "running")
                and not studio.graph.finished()
            )
            if unfinished:
                foreman.start()
        return self.foremen[world_id]

    def reset(self) -> None:
        """Drop cached foremen (after a model key is connected, they use it)."""
        self.foremen = {
            w: f for w, f in self.foremen.items() if f._runner is not None and not f._runner.done()
        }


def install(app: FastAPI, the_hub) -> None:
    studios = StudioHub(the_hub())
    app.state.studios = studios

    def foreman_for(world_id: str) -> Foreman:
        try:
            return studios.foreman(world_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"no world {world_id}") from exc

    @app.post("/api/studio")
    async def start(request: GoalRequest) -> dict:
        goal = request.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="A goal is needed.")
        hub = the_hub()
        world_id = hub.store.create_world(goal, datetime(2000, 1, 1, 8))
        foreman = studios.foreman(world_id, auto=request.auto)
        foreman.submit(goal, budget=request.budget)
        return {"world_id": world_id, "backend": "model" if hub.llm is not None else "sim"}

    @app.post("/api/studio/{world_id}/goal")
    async def new_goal(world_id: str, request: GoalRequest) -> dict:
        """A new goal on a world that exists: it changes the world, it does not rebuild it."""
        foreman = foreman_for(world_id)
        goal = request.goal.strip()
        if not goal:
            raise HTTPException(status_code=422, detail="A goal is needed.")
        try:
            foreman.submit(goal, budget=request.budget)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"world_id": world_id}

    @app.get("/api/studio/{world_id}")
    async def snapshot(world_id: str) -> dict:
        return foreman_for(world_id).studio.snapshot()

    @app.get("/api/studio/{world_id}/draft")
    async def draft(world_id: str) -> dict:
        return foreman_for(world_id).draft_view()

    @app.get("/api/studio/{world_id}/audit")
    async def audit(world_id: str) -> list[dict]:
        studio = foreman_for(world_id).studio
        return [a.model_dump(mode="json") for a in studio.data.audit]

    @app.post("/api/studio/{world_id}/decisions/{decision_id}/answer")
    async def answer(world_id: str, decision_id: str, request: AnswerRequest) -> dict:
        studio = foreman_for(world_id).studio
        try:
            decision = studio.answer(decision_id, request.option, request.text)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return decision.model_dump(mode="json")

    @app.post("/api/studio/{world_id}/merge")
    async def merge(world_id: str, request: MergeRequest) -> dict:
        """Answer the open merge decision: merge all, or some and send the rest back."""
        studio = foreman_for(world_id).studio
        pending = next(
            (d for d in studio.data.decisions if d.kind == "merge" and d.status == "open"), None
        )
        if pending is None:
            raise HTTPException(status_code=409, detail="There is no merge waiting.")
        note = json.dumps({"merge": request.merge, "send_back": request.send_back})
        option = "Merge anyway" if "Merge anyway" in pending.options else "Merge"
        studio.answer(pending.id, option, note)
        return {"answered": pending.id}

    @app.post("/api/studio/{world_id}/console")
    async def console(world_id: str, request: ConsoleRequest) -> dict:
        return {"lines": await foreman_for(world_id).command(request.text)}

    @app.post("/api/studio/{world_id}/message")
    async def message(world_id: str, request: MessageRequest) -> dict:
        foreman = foreman_for(world_id)
        target = foreman.names().get(request.to.lstrip("@").lower())
        if target is None or not request.text.strip():
            raise HTTPException(status_code=422, detail="Name a teammate and say something.")
        foreman.studio.send(target, request.text.strip(), "you")
        foreman.studio.log("you", "message", f"{target}: {request.text.strip()}")
        return {"to": target}

    @app.post("/api/studio/{world_id}/agents/{agent_id}/{action}")
    async def agent_action(world_id: str, agent_id: str, action: str) -> dict:
        foreman = foreman_for(world_id)
        if agent_id not in {a.id for a in foreman.studio.data.agents}:
            raise HTTPException(status_code=404, detail=f"no agent {agent_id}")
        if action == "pause":
            foreman.pause_agent(agent_id)
        elif action in ("resume", "spawn"):
            foreman.resume_agent(agent_id)
            foreman.start()
        elif action == "stop":
            await foreman.stop_agent(agent_id)
        else:
            raise HTTPException(status_code=422, detail="action is pause, resume, stop or spawn")
        return {"ok": True}

    @app.put("/api/studio/{world_id}/memory")
    async def write_memory(world_id: str, request: MemoryRequest) -> dict:
        studio = foreman_for(world_id).studio
        if not request.title.strip() or not request.body.strip():
            raise HTTPException(status_code=422, detail="A note needs a title and a body.")
        entry = studio.remember(request.title, request.body, "you", request.scope)
        studio.log("you", "note", entry.title)
        return entry.model_dump(mode="json")

    @app.delete("/api/studio/{world_id}/memory/{entry_id}")
    async def delete_memory(world_id: str, entry_id: str) -> dict:
        if not foreman_for(world_id).studio.forget(entry_id):
            raise HTTPException(status_code=404, detail="No such note.")
        return {"deleted": entry_id}

    @app.post("/api/studio/{world_id}/budget")
    async def budget(world_id: str, request: BudgetRequest) -> dict:
        if request.amount <= 0:
            raise HTTPException(status_code=422, detail="The budget must be more than zero.")
        studio = foreman_for(world_id).studio
        studio.update_goal(budget=request.amount)
        studio.log("you", "budget", f"${request.amount:.2f}")
        return {"budget": request.amount}

    @app.get("/api/studio/{world_id}/town")
    async def town(world_id: str) -> dict:
        """The people of the merged world, for the studio's Town tab."""
        foreman_for(world_id)
        hub = the_hub()
        from tinyworld.core import branches

        found = list(branches.tree(hub.store, world_id))
        if not found:
            return {"branch_id": None, "people": []}
        branch = found[-1]
        state = hub.session(branch.id).state
        people = []
        for person in state.people():
            last = hub.store.events(branch.id, actor=person.id, limit=1, newest_first=True)
            here = state.entities.get(person.location) if person.location else None
            people.append({
                "id": person.id, "name": person.name,
                "occupation": person.attrs.get("occupation", ""),
                "place": here.name if here else "",
                "doing": last[0].narration if last else "",
                "alive": person.alive,
            })
        return {"branch_id": branch.id, "people": people}

    @app.post("/api/studio/{world_id}/stop")
    async def stop(world_id: str) -> dict:
        await foreman_for(world_id).stop()
        return {"stopped": True}

    @app.post("/api/studio/{world_id}/resume")
    async def resume(world_id: str) -> dict:
        foreman = foreman_for(world_id)
        foreman.start()
        return {"running": True}

    @app.websocket("/ws/studio/{world_id}")
    async def studio_socket(socket: WebSocket, world_id: str) -> None:
        try:
            foreman = studios.foreman(world_id)
        except KeyError:
            await socket.close(code=4404)
            return
        studio = foreman.studio
        queue = studio.bus.subscribe()
        await socket.accept()
        try:
            await socket.send_text(json.dumps(studio.snapshot()))
            closed = asyncio.create_task(socket.receive())
            while True:
                message = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {message, closed}, return_when=asyncio.FIRST_COMPLETED
                )
                if closed in done:
                    if closed.result().get("type") == "websocket.disconnect":
                        message.cancel()
                        break
                    closed = asyncio.create_task(socket.receive())
                if message in done:
                    await socket.send_text(json.dumps(message.result()))
                else:
                    message.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            studio.bus.unsubscribe(queue)
