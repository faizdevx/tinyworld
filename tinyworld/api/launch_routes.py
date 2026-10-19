"""One door into everything: type a scenario, the team builds it, the town opens.

    POST /api/launch                {scenario}       -> {world_id}
    GET  /api/launch/{world_id}                      -> progress: stage, tasks, feed, what is being asked
    POST /api/launch/{world_id}/enter                -> {branch_id}   (once the world is merged)

The build runs in auto mode so nothing waits for a person: the lead plans, researchers read the web,
writers fill in the sections, the reviewer checks them, and the draft is merged when it is sound.
Whatever the model (a local open-weight server, or the offline stand-in) is, this is the same path.
"""

from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class LaunchRequest(BaseModel):
    scenario: str
    budget: float | None = None


def stage_of(studio) -> str:
    goal = studio.data.goal
    if goal is None:
        return "starting"
    if goal.status == "merged":
        return "ready"
    if goal.status in ("rejected", "failed"):
        return "failed"
    if goal.status == "paused":
        return "paused"
    return "building"


def install(app: FastAPI, the_hub) -> None:
    def foreman(world_id: str):
        try:
            return app.state.studios.foreman(world_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"no world {world_id}") from exc

    @app.post("/api/launch")
    async def launch(request: LaunchRequest) -> dict:
        text = request.scenario.strip()
        if len(text) < 8:
            raise HTTPException(status_code=422, detail="Describe the scenario in a sentence or two.")
        hub = the_hub()
        world_id = hub.store.create_world(text, datetime(2000, 1, 1, 8))
        f = app.state.studios.foreman(world_id, auto=True)
        f.submit(text, budget=request.budget)
        return {"world_id": world_id, "backend": "model" if hub.llm is not None else "sim"}

    @app.get("/api/launch/{world_id}")
    async def progress(world_id: str) -> dict:
        f = foreman(world_id)
        studio = f.studio
        tasks = studio.graph.all()
        done = [t for t in tasks if t.status == "done"]
        agents = {a.id: a for a in studio.data.agents}
        dollars, calls = studio.spend()
        hub = the_hub()
        branches = hub.store.branches(world_id)
        return {
            "world_id": world_id,
            "scenario": studio.data.goal.text if studio.data.goal else hub.store.world(world_id)["premise"],
            "stage": stage_of(studio),
            "progress": round(len(done) / len(tasks), 3) if tasks else 0.0,
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status, "kind": t.kind,
                 "who": agents[t.assignee].name if t.assignee in agents else ""}
                for t in tasks
            ],
            "feed": [{"text": x.text, "kind": x.kind} for x in studio.data.feed[-14:]],
            "asking": [d.question for d in studio.open_decisions()],
            "sections": sorted(studio.data.draft),
            "calls": calls, "dollars": round(dollars, 4),
            "branch_id": branches[0]["id"] if branches else None,
            "backend": "model" if hub.llm is not None else "sim",
        }

    @app.post("/api/launch/{world_id}/enter")
    async def enter(world_id: str) -> dict:
        f = foreman(world_id)
        if stage_of(f.studio) != "ready":
            raise HTTPException(status_code=409, detail="The world is not built yet.")
        hub = the_hub()
        branches = hub.store.branches(world_id)
        if branches:
            return {"branch_id": branches[0]["id"]}
        try:
            session, _ = hub.pipeline().seed(world_id, "main")
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        hub.adopt(session)
        return {"branch_id": session.branch_id}
