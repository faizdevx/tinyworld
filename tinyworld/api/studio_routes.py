"""HTTP and WebSocket routes for the studio: the team that builds a world."""

import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from tinyworld.core.store import StoreError
from tinyworld.studio.sim import ScriptedTeam, scripted_search
from tinyworld.studio.state import Studio
from tinyworld.studio.team import Foreman


class GoalRequest(BaseModel):
    goal: str
    # Hold every decision for the user (the default), or let the team decide.
    auto: bool = False


class AnswerRequest(BaseModel):
    option: str = ""
    text: str = ""


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

                llm = StructuredLLM(ScriptedTeam(delay=0.4), hub.config, hub.tracer)
                search = scripted_search(goal)
            self.foremen[world_id] = Foreman(
                studio, llm, search, auto_answer=auto, max_parallel=3
            )
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
        foreman.submit(goal)
        return {"world_id": world_id, "backend": "model" if hub.llm is not None else "sim"}

    @app.get("/api/studio/{world_id}")
    async def snapshot(world_id: str) -> dict:
        return foreman_for(world_id).studio.snapshot()

    @app.get("/api/studio/{world_id}/draft")
    async def draft(world_id: str) -> dict:
        return foreman_for(world_id).draft_view()

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
