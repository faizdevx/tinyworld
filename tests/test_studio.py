import asyncio
from datetime import datetime

import pytest

from tinyworld.core.store import Store
from tinyworld.genesis import critic
from tinyworld.genesis.bible import BibleStore
from tinyworld.genesis.pipeline import GenesisPipeline
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import LLMResult
from tinyworld.studio.protocol import PROTOCOL_VERSION, Decision
from tinyworld.studio.session import AgentSession, Tool
from tinyworld.studio.sim import ScriptedTeam, scripted_search
from tinyworld.studio.state import Studio
from tinyworld.studio.taskgraph import TaskError, TaskGraph
from tinyworld.studio.team import Foreman, standard_plan

GOAL = "What if India never had Jio internet in 2016. Lucknow, Uttar Pradesh."


def run(coroutine):
    return asyncio.run(coroutine)


def build(goal=GOAL, *, auto=True, client=None, **options):
    store = Store()
    world = store.create_world(goal, datetime(2000, 1, 1, 8))
    studio = Studio(store, world)
    config = LLMConfig()
    llm = StructuredLLM(client or ScriptedTeam(), config, Tracer(store, config))
    foreman = Foreman(studio, llm, scripted_search(goal), auto_answer=auto, **options)
    return store, world, studio, foreman


# -- the task graph -----------------------------------------------------------


def test_a_task_waits_for_its_dependencies_and_needs_someone_assigned():
    graph = TaskGraph()
    a = graph.create("research")
    b = graph.create("write", deps=[a.id])
    assert [t.id for t in graph.ready()] == [a.id]
    with pytest.raises(TaskError, match="waits on"):
        graph.move(b.id, "doing", assignee="juno")
    with pytest.raises(TaskError, match="nobody assigned"):
        graph.move(a.id, "doing")
    graph.move(a.id, "doing", assignee="iris")
    graph.move(a.id, "done")
    assert [t.id for t in graph.ready()] == [b.id]
    assert graph.progress() == 0.5


def test_dependencies_must_exist_and_may_not_loop():
    graph = TaskGraph()
    a = graph.create("a")
    b = graph.create("b", deps=[a.id])
    with pytest.raises(TaskError, match="unknown"):
        graph.create("c", deps=["t99"])
    with pytest.raises(TaskError, match="wait on itself"):
        graph.set_deps(a.id, [b.id])
    with pytest.raises(TaskError, match="wait on itself"):
        graph.set_deps(a.id, [a.id])


def test_a_finished_task_cannot_be_moved_somewhere_odd():
    graph = TaskGraph()
    a = graph.create("a")
    graph.move(a.id, "done")
    with pytest.raises(TaskError, match="cannot go from"):
        graph.move(a.id, "review")


def test_the_standard_plan_has_the_right_shape():
    plan = standard_plan(["a", "b"])
    kinds = [t["kind"] for t in plan]
    assert kinds.count("research") == 2 and kinds[-2:] == ["review", "digest"]
    sections = [t.get("section") for t in plan if t["kind"] == "section"]
    assert sections.index("figures") > sections.index("geography")
    assert sections.index("tensions") > sections.index("figures")
    figures = next(t for t in plan if t.get("section") == "figures")
    assert len(figures["deps"]) == 3


# -- one agent, one task ------------------------------------------------------


class Scripted:
    """A client that plays back a list of steps, then repeats the last."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    async def complete(self, request, model, effort):
        self.requests.append(request)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        import json

        return LLMResult(text=json.dumps(step), model="m")


def session_for(client, tools, **options):
    config = LLMConfig()
    store = Store()
    llm = StructuredLLM(client, config, Tracer(store, config), max_repairs=0)
    return AgentSession(
        llm, world_id="w", agent_id="a", name="Ann", role="tester", tools=tools, **options
    )


async def echo(args):
    return "result: " + str(args.get("x"))


def test_a_session_uses_tools_and_stops_when_it_finishes():
    client = Scripted([
        {"tool": "echo", "args": {"x": 1}},
        {"tool": "finish", "args": {"summary": "all done"}},
    ])
    result = run(session_for(client, [Tool("echo", "echo(x)", echo)]).run("task"))
    assert (result.status, result.summary, result.used) == ("finished", "all done", ["echo"])
    # The tool result reached the next prompt, quoted as material, not an order.
    assert "<tool_result>" in client.requests[1].user and "result: 1" in client.requests[1].user


def test_a_session_cannot_run_forever():
    client = Scripted([{"tool": "echo", "args": {"x": 1}}])
    result = run(session_for(client, [Tool("echo", "echo(x)", echo)], max_steps=4).run("task"))
    assert result.status == "capped" and result.steps == 4


def test_an_unknown_tool_is_an_observation_not_a_crash():
    client = Scripted([
        {"tool": "delete_everything", "args": {}},
        {"tool": "finish", "args": {"summary": "ok"}},
    ])
    result = run(session_for(client, [Tool("echo", "echo(x)", echo)]).run("task"))
    assert result.status == "finished"
    assert "no tool 'delete_everything'" in client.requests[1].user.replace("There is ", "")


def test_a_tool_that_raises_is_reported_to_the_agent():
    async def boom(args):
        raise RuntimeError("disk full")

    client = Scripted([
        {"tool": "boom", "args": {}},
        {"tool": "finish", "args": {"summary": "ok"}},
    ])
    result = run(session_for(client, [Tool("boom", "boom()", boom)]).run("task"))
    assert result.status == "finished"
    assert "boom failed: RuntimeError: disk full" in client.requests[1].user


def test_the_same_call_a_third_time_is_refused():
    client = Scripted([
        {"tool": "echo", "args": {"x": 1}},
        {"tool": "echo", "args": {"x": 1}},
        {"tool": "echo", "args": {"x": 1}},
        {"tool": "finish", "args": {"summary": "ok"}},
    ])
    calls = []

    async def counting(args):
        calls.append(args)
        return "ran"

    run(session_for(client, [Tool("echo", "echo(x)", counting)]).run("task"))
    assert len(calls) == 2
    assert "exact call twice" in client.requests[3].user


# -- the whole team -----------------------------------------------------------


def test_a_scripted_team_builds_a_world_and_nothing_is_live_until_it_is_merged():
    store, world, studio, foreman = build(auto=False)
    bibles = BibleStore(store)

    async def drive():
        foreman.submit(GOAL)
        for _ in range(1000):
            await asyncio.sleep(0.005)
            for d in studio.open_decisions():
                if d.kind == "question":
                    studio.answer(d.id, d.options[0])
            if any(d.kind == "merge" for d in studio.data.decisions):
                break
        merge = next(d for d in studio.data.decisions if d.kind == "merge")
        # A full draft exists, and the world has nothing in it yet.
        assert "figures" in studio.data.draft and "digest" in studio.data.draft
        assert bibles.get(world, "geography") is None
        assert studio.data.goal.status == "review"
        studio.answer(merge.id, "Merge")
        await foreman.wait()

    run(drive())
    assert studio.data.goal.status == "merged"
    assert bibles.get(world, "geography").places
    assert len(bibles.get(world, "figures").figures) >= 8
    assert bibles.get(world, "digest") is not None
    assert [f for f in critic.check(bibles.load(world)) if f.blocking] == []
    # And the merged world seeds like any other.
    genesis = GenesisPipeline(store, StructuredLLM(FakeLLM({}), LLMConfig()))
    session, _ = genesis.seed(world)
    assert len(session.state.people()) >= 8


def test_a_rejected_draft_changes_nothing():
    store, world, studio, foreman = build(auto=False)

    async def drive():
        foreman.submit(GOAL)
        for _ in range(1000):
            await asyncio.sleep(0.005)
            for d in studio.open_decisions():
                if d.kind == "question":
                    studio.answer(d.id, d.options[0])
            if any(d.kind == "merge" for d in studio.data.decisions):
                break
        merge = next(d for d in studio.data.decisions if d.kind == "merge")
        studio.answer(merge.id, "Reject")
        await foreman.wait()

    run(drive())
    assert studio.data.goal.status == "rejected"
    assert BibleStore(store).get(world, "geography") is None
    assert studio.data.merged_version is None


def test_agents_work_in_parallel_up_to_the_limit():
    class Slow(ScriptedTeam):
        active = 0
        peak = 0

        async def complete(self, request, model, effort):
            Slow.active += 1
            Slow.peak = max(Slow.peak, Slow.active)
            await asyncio.sleep(0.01)
            try:
                return await super().complete(request, model, effort)
            finally:
                Slow.active -= 1

    store, world, studio, foreman = build(client=Slow(ask=False), max_parallel=3)

    async def drive():
        foreman.submit(GOAL)
        await foreman.wait()

    run(drive())
    assert Slow.peak >= 2
    assert max(
        sum(1 for t in studio.graph.all() if t.status == "doing") for _ in [0]
    ) == 0  # nothing left running


def test_what_an_agent_is_doing_comes_from_the_tools_it_uses():
    store, world, studio, foreman = build(client=ScriptedTeam(ask=False))
    queue = studio.bus.subscribe(size=5000)

    async def drive():
        foreman.submit(GOAL)
        await foreman.wait()

    run(drive())
    seen = set()
    while not queue.empty():
        msg = queue.get_nowait()
        if msg["type"] == "agent.upsert":
            seen.add((msg["agent"]["state"], msg["agent"]["station"]))
    assert ("researching", "web") in seen
    assert ("writing", "drafting") in seen
    assert ("thinking", "wall") in seen
    assert ("reviewing", "review") in seen


def test_a_question_reaches_the_user_and_the_answer_goes_back_to_the_agent():
    store, world, studio, foreman = build(auto=False)
    answered = {}

    async def drive():
        foreman.submit(GOAL)
        for _ in range(1000):
            await asyncio.sleep(0.005)
            for d in studio.open_decisions():
                if d.kind == "question":
                    answered["q"] = d.question
                    studio.answer(d.id, d.options[1])
            if any(d.kind == "merge" for d in studio.data.decisions):
                break
        await foreman.stop()

    run(drive())
    assert "real, living public figures" in answered["q"]
    decision = next(d for d in studio.data.decisions if d.kind == "question")
    assert decision.status == "answered" and decision.answer == "Allow historical figures"


def test_a_bad_section_is_refused_with_what_to_fix():
    store, world, studio, foreman = build(client=ScriptedTeam(ask=False))
    tools = {t.name: t for t in foreman._tools(
        studio.graph.create("w", kind="section", section="geography"),
        studio.agent("juno"),
    )}
    reply = run(tools["write_section"].run({"section": "geography", "content": {"places": "no"}}))
    assert "was not saved" in reply and "places" in reply
    assert "geography" not in studio.data.draft
    reply = run(tools["write_section"].run({"section": "nonsense", "content": {}}))
    assert "is not a section" in reply


# -- durability ---------------------------------------------------------------


def test_state_survives_a_restart_and_running_work_goes_back_on_the_wall():
    store, world, studio, foreman = build()
    task = studio.graph.create("write geography", kind="section", section="geography")
    studio.graph.move(task.id, "doing", assignee="juno")
    studio.task_changed(task.id)
    studio.remember("Notes", "Chowk is old", "iris")
    studio.set_goal("a goal")
    studio.save()

    again = Studio(store, world)
    assert again.data.goal.text == "a goal"
    assert again.graph.get(task.id).status == "todo"
    assert again.graph.get(task.id).assignee is None
    assert again.data.memory[0].body == "Chowk is old"
    assert {a.id for a in again.data.agents} >= {"marlow", "iris", "vera"}
    assert all(a.state == "idle" for a in again.data.agents)


def test_a_snapshot_is_a_versioned_message_a_viewer_can_draw():
    store, world, studio, foreman = build()
    snap = studio.snapshot()
    assert snap["v"] == PROTOCOL_VERSION and snap["type"] == "snapshot"
    assert {a["id"] for a in snap["agents"]} >= {"marlow", "juno", "vera"}
    assert set(snap) >= {"goal", "agents", "tasks", "decisions", "memory", "feed"}


def test_answering_twice_or_with_a_made_up_option_is_refused():
    store, world, studio, foreman = build()

    async def scenario():
        future = studio.ask(
            Decision(id="", agent_id="marlow", question="q?", options=["a", "b"])
        )
        decision = studio.data.decisions[0]
        with pytest.raises(ValueError, match="not one of"):
            studio.answer(decision.id, "c")
        studio.answer(decision.id, "a")
        with pytest.raises(ValueError, match="already"):
            studio.answer(decision.id, "b")
        return (await future).answer

    assert run(scenario()) == "a"


# -- the API ------------------------------------------------------------------


def test_the_studio_api_builds_a_world_with_no_model_and_the_user_merges_it(monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from tinyworld.api.app import create_app
    from tinyworld.api.hub import Hub

    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY", "TINYWORLD_PROVIDER", "LOCAL_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    def wait(client, world, predicate, seconds=20):
        end = time.time() + seconds
        while time.time() < end:
            snap = client.get(f"/api/studio/{world}").json()
            if predicate(snap):
                return snap
            time.sleep(0.03)
        raise AssertionError("timed out")

    with TestClient(create_app(Hub())) as client:
        started = client.post("/api/studio", json={"goal": GOAL}).json()
        assert started["backend"] == "sim"
        world = started["world_id"]

        # The team asks a question on the way; answer it from the page.
        question = wait(
            client, world, lambda s: any(d["kind"] == "question" and d["status"] == "open" for d in s["decisions"])
        )
        qid = next(d["id"] for d in question["decisions"] if d["kind"] == "question")
        assert client.post(
            f"/api/studio/{world}/decisions/{qid}/answer", json={"option": "Yes, invent everyone"}
        ).status_code == 200
        assert client.post(
            f"/api/studio/{world}/decisions/{qid}/answer", json={"option": "Yes, invent everyone"}
        ).status_code == 409

        snap = wait(client, world, lambda s: any(d["kind"] == "merge" for d in s["decisions"]))
        assert snap["goal"]["status"] == "review"
        draft = client.get(f"/api/studio/{world}/draft").json()
        assert "figures" in draft["draft"] and draft["merged_version"] is None
        # Not the world yet.
        assert client.get(f"/api/worlds/{world}/bible").json()["bible"]["geography"]["places"] == []

        mid = next(d["id"] for d in snap["decisions"] if d["kind"] == "merge")
        client.post(f"/api/studio/{world}/decisions/{mid}/answer", json={"option": "Merge"})
        wait(client, world, lambda s: s["goal"]["status"] == "merged")
        bible = client.get(f"/api/worlds/{world}/bible").json()["bible"]
        assert len(bible["figures"]["figures"]) >= 8

        seeded = client.post(f"/api/worlds/{world}/seed", json={"name": "main"})
        assert seeded.status_code == 200 and seeded.json()["branch_id"]

        with client.websocket_connect(f"/ws/studio/{world}") as socket:
            first = socket.receive_json()
        assert first["type"] == "snapshot" and first["goal"]["status"] == "merged"

        assert client.get("/api/studio/nope").status_code == 404
        assert client.post("/api/studio", json={"goal": "  "}).status_code == 422
