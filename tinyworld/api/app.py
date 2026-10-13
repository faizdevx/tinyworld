"""HTTP API. ``python -m tinyworld.api.app`` serves it on port 8000."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tinyworld.api.hub import Hub
from tinyworld.core.events import Intent
from tinyworld.core.store import StoreError
from tinyworld.fixtures import toy
from tinyworld.sim.step import apply_intents

STATIC = Path(__file__).parent / "static"


class IntentsRequest(BaseModel):
    intents: list[Intent]


def create_app(hub: Hub | None = None) -> FastAPI:
    app = FastAPI(title="TinyWorld")
    app.state.hub = hub or Hub()

    def session_for(branch_id: str):
        try:
            return app.state.hub.session(branch_id)
        except StoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/debug")
    async def debug_page() -> FileResponse:
        return FileResponse(STATIC / "debug.html")

    @app.get("/api/status")
    async def status() -> dict:
        return {"model_configured": app.state.hub.has_model}

    @app.post("/api/worlds/toy")
    async def create_toy() -> dict:
        session = app.state.hub.adopt(toy.build_toy(app.state.hub.store))
        return {"world_id": session.world_id, "branch_id": session.branch_id}

    @app.get("/api/branches/{branch_id}/state")
    async def state(branch_id: str) -> dict:
        return session_for(branch_id).state.model_dump(mode="json")

    @app.get("/api/branches/{branch_id}/events")
    async def events(branch_id: str, after: int = 0, limit: int = 200) -> list[dict]:
        session_for(branch_id)
        found = app.state.hub.store.events(branch_id, after=after, limit=limit)
        return [event.model_dump(mode="json") for event in found]

    @app.post("/api/branches/{branch_id}/intents")
    async def intents(branch_id: str, request: IntentsRequest) -> dict:
        session = session_for(branch_id)
        result = await apply_intents(
            session, app.state.hub.game_master(branch_id), request.intents
        )
        return {
            "outcomes": [o.model_dump(mode="json") for o in result.outcomes],
            "events": [e.model_dump(mode="json") for e in result.events],
            "observations": [o.model_dump(mode="json") for o in result.observations],
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
