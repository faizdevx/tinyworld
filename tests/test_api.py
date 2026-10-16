import copy
import json
import time

import pytest
from fastapi.testclient import TestClient

from tinyworld.api.app import create_app
from tinyworld.api.hub import Hub
from tinyworld.fixtures import berlin, toy


@pytest.fixture
def api(monkeypatch):
    """An offline server: no model, rule-driven agents, canned bible."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with TestClient(create_app(Hub())) as client:
        yield client


def wait_for_genesis(api, world_id, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        world = api.get(f"/api/worlds/{world_id}").json()
        if not world["genesis"]["running"] and world["genesis"]["stage"] not in ("queued",):
            return world
        time.sleep(0.05)
    raise AssertionError("genesis did not finish")


def new_world(api):
    world_id = api.post("/api/worlds", json={"premise": berlin.PREMISE_TEXT}).json()["world_id"]
    wait_for_genesis(api, world_id)
    branch_id = api.post(f"/api/worlds/{world_id}/seed", json={"name": "main"}).json()["branch_id"]
    return world_id, branch_id


def toy_branch(api):
    return api.post("/api/worlds/toy").json()["branch_id"]


# -- pages and status --------------------------------------------------------


def test_root_redirects_to_the_app_and_status_reports_offline_mode(api):
    assert api.get("/", follow_redirects=False).headers["location"] == "/app/"
    assert api.get("/app/").status_code == 200
    status = api.get("/api/status").json()
    assert status["model_configured"] is False and status["offline"] is True
    assert set(status["tiers"]) == {"strong", "standard", "cheap"}


def test_without_a_model_or_fallback_genesis_is_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with TestClient(create_app(Hub(offline_fallback=False))) as client:
        assert client.post("/api/worlds", json={"premise": "x"}).status_code == 503


# -- genesis -----------------------------------------------------------------


def test_premise_to_reviewed_bible_to_seeded_branch(api):
    assert api.post("/api/worlds", json={"premise": "  "}).status_code == 422
    world_id = api.post("/api/worlds", json={"premise": berlin.PREMISE_TEXT}).json()["world_id"]
    world = wait_for_genesis(api, world_id)

    genesis = world["genesis"]
    assert genesis["stage"] == "done" and genesis["error"] == "" and genesis["questions"] == []
    assert [entry["stage"] for entry in genesis["log"]][0] == "premise"
    assert world["offline"] is True and world["branches"] == []

    bible = api.get(f"/api/worlds/{world_id}/bible").json()
    assert bible["version"] == 0
    assert len(bible["bible"]["figures"]["figures"]) == 10
    assert bible["bible"]["digest"]["overview"].startswith("Falkenrode")

    listed = api.get("/api/worlds").json()
    assert listed[0]["id"] == world_id and listed[0]["stage"] == "done"

    seeded = api.post(f"/api/worlds/{world_id}/seed", json={"name": "main"}).json()
    assert seeded["notes"] == []
    branch = api.get(f"/api/branches/{seeded['branch_id']}").json()
    assert branch["name"] == "main" and branch["status"]["population"] == 10
    assert branch["status"]["sim_time"] == "1941-09-15T08:00:00"
    assert api.get(f"/api/worlds/{world_id}").json()["branches"][0]["id"] == seeded["branch_id"]


def test_bible_edit_validates_versions_and_reports_findings(api):
    world_id, _ = new_world(api)
    figures = copy.deepcopy(berlin.FIGURES)
    figures["figures"][0]["home"] = "Castle Dracula"
    edited = api.put(f"/api/worlds/{world_id}/bible/figures", json=figures).json()
    assert edited["version"] == 1
    assert any("Castle Dracula" in f["text"] for f in edited["findings"])
    assert any("Castle Dracula" in f["text"] for f in api.get(f"/api/worlds/{world_id}").json()["genesis"]["findings"])

    assert api.put(f"/api/worlds/{world_id}/bible/figures", json={"figures": [{"name": "x"}]}).status_code == 422
    assert api.put(f"/api/worlds/{world_id}/bible/nonsense", json={}).status_code == 422
    old = api.get(f"/api/worlds/{world_id}/bible", params={"version": 0}).json()
    assert old["bible"]["figures"]["figures"][0]["home"] == "Keller Bakery"

    reseeded = api.post(f"/api/worlds/{world_id}/seed", json={"name": "second"}).json()
    assert any("Castle Dracula" in note["text"] for note in reseeded["notes"])
    assert api.get(f"/api/worlds/{world_id}/sources").json() == []
    assert api.get("/api/worlds/nope").status_code == 404


def test_thin_premise_asks_and_an_answer_restarts_genesis(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    hub = Hub()
    asked = {"n": 0}
    original = hub.genesis_llm

    def genesis_llm(*_):
        llm = original()
        def premise(request):
            asked["n"] += 1
            return {"questions": ["When and where?"]} if asked["n"] == 1 else berlin.PREMISE
        llm.client.on("genesis.premise", premise)
        return llm

    hub.genesis_llm = genesis_llm
    with TestClient(create_app(hub)) as client:
        world_id = client.post("/api/worlds", json={"premise": "A town."}).json()["world_id"]
        world = wait_for_genesis(client, world_id)
        assert world["genesis"]["stage"] == "premise"
        assert world["genesis"]["questions"] == ["When and where?"]

        client.post(f"/api/worlds/{world_id}/genesis/answer", json={"text": "Near Berlin, 1941."})
        world = wait_for_genesis(client, world_id)
        assert world["genesis"]["stage"] == "done" and "Near Berlin, 1941." in world["premise"]

        client.post(f"/api/worlds/{world_id}/genesis/stage", json={"stage": "digest"})
        assert wait_for_genesis(client, world_id)["genesis"]["stage"] == "done"
        client.post(f"/api/worlds/{world_id}/genesis/stage", json={"stage": "bogus"})
        assert "unknown stage" in wait_for_genesis(client, world_id)["genesis"]["error"]


# -- running a world ---------------------------------------------------------


def test_step_events_people_and_agent_inspection(api):
    _, branch = new_world(api)
    seeded = api.get(f"/api/branches/{branch}").json()["head_seq"]
    for _ in range(4):
        stepped = api.post(f"/api/branches/{branch}/run", json={"action": "step"}).json()
        assert stepped["paused"] is False
    status = stepped["status"]
    assert status["seq"] > seeded and status["running"] is False and status["cost"] > 0

    events = api.get(f"/api/branches/{branch}/events", params={"after": seeded}).json()
    assert len(events) > 10 and events[0]["seq"] == seeded + 1
    newest = api.get(f"/api/branches/{branch}/events", params={"newest": True, "limit": 3}).json()
    assert [e["seq"] for e in newest] == [status["seq"], status["seq"] - 1, status["seq"] - 2]
    spoken = api.get(f"/api/branches/{branch}/events", params={"kind": "utterance"}).json()
    assert all(e["kind"] == "utterance" for e in spoken)

    people = api.get(f"/api/branches/{branch}/people").json()
    assert len(people) == 10 and all(p["has_persona"] for p in people)

    anna = api.get(f"/api/branches/{branch}/agents/person:anna_keller").json()
    assert anna["name"] == "Anna Keller" and anna["location_name"]
    assert anna["persona"]["secrets"] == ["hides two sacks of flour from the food office"]
    assert "persona" not in anna["attrs"] and anna["attrs"]["birth_date"]
    assert anna["memories"]["count"] > 0 and anna["memories"]["recent"]
    assert anna["thought"] and anna["cost"] > 0
    # Conversations in the steps may nudge trust, so test that the bond is still there, not its exact value.
    assert any(r["name"] == "Lena Vogel" and r["theirs"]["value"] >= 40 for r in anna["relations"])
    assert {i["name"] for i in anna["inventory"]} >= {"reichsmark"}
    assert api.get(f"/api/branches/{branch}/agents/place:town_hall").status_code == 404
    assert api.get("/api/branches/nope/people").status_code == 404
    assert api.post(f"/api/branches/{branch}/run", json={"action": "dance"}).status_code == 422


def test_beliefs_are_shown_against_the_truth(api):
    branch = toy_branch(api)
    api.post(
        f"/api/branches/{branch}/intents",
        json={"intents": [{"agent": toy.LENA, "verb": "move", "target": toy.BAKERY}]},
    )
    hub = api.app.state.hub
    runner = hub.runner(branch)
    from tinyworld.agents.beliefs import Belief

    runner.sim.beliefs.add(
        branch,
        Belief(agent=toy.LENA, subject=toy.GRAIN, predicate="rationed", value=False, confidence=0.85,
               source=toy.ANNA, origin="communication", as_of_seq=8, as_of=runner.session.state.sim_time),
    )
    lena = api.get(f"/api/branches/{branch}/agents/{toy.LENA}").json()
    belief = lena["beliefs"][0]
    assert belief["correct"] is False and belief["actual"] is True and belief["source_name"] == "Anna Keller"


def test_play_and_pause(api):
    branch = toy_branch(api)
    started = api.post(f"/api/branches/{branch}/run", json={"action": "play", "delay": 0}).json()
    assert started["status"]["running"] is True and started["status"]["delay"] == 0
    deadline = time.time() + 10
    while time.time() < deadline and api.get(f"/api/branches/{branch}").json()["head_seq"] < 20:
        time.sleep(0.05)
    paused = api.post(f"/api/branches/{branch}/run", json={"action": "pause"}).json()
    assert paused["status"]["running"] is False
    head = api.get(f"/api/branches/{branch}").json()["head_seq"]
    assert head >= 20
    time.sleep(0.2)
    assert api.get(f"/api/branches/{branch}").json()["head_seq"] == head


def test_budget_pauses_a_running_world_and_can_be_raised(api):
    branch = toy_branch(api)
    api.post(f"/api/branches/{branch}/run", json={"action": "step"})
    spent = api.get(f"/api/branches/{branch}").json()["status"]["cost"]
    capped = api.post(f"/api/branches/{branch}/budget", json={"run_cap": spent}).json()
    assert capped["status"]["level"] == "pause"
    stepped = api.post(f"/api/branches/{branch}/run", json={"action": "step"}).json()
    assert stepped["paused"] is True and stepped["events"] == []
    raised = api.post(f"/api/branches/{branch}/budget", json={"add": spent * 10}).json()
    assert raised["status"]["level"] == "ok"
    assert api.post(f"/api/branches/{branch}/run", json={"action": "step"}).json()["paused"] is False


def test_websocket_streams_status_and_events(api):
    branch = toy_branch(api)
    with api.websocket_connect(f"/ws/branches/{branch}") as socket:
        first = json.loads(socket.receive_text())
        assert first["type"] == "status" and first["status"]["branch_id"] == branch
        api.post(f"/api/branches/{branch}/run", json={"action": "step"})
        kinds = []
        for _ in range(3):
            message = json.loads(socket.receive_text())
            kinds.append(message["type"])
            if message["type"] == "events":
                assert message["events"][0]["branch_id"] == branch
        # Stepping first makes sure nothing is playing, then reports what happened.
        assert kinds == ["status", "events", "status"]
        assert message["status"]["seq"] > first["status"]["seq"]


def test_world_socket_reports_genesis(api):
    world_id = api.post("/api/worlds", json={"premise": berlin.PREMISE_TEXT}).json()["world_id"]
    with api.websocket_connect(f"/ws/worlds/{world_id}") as socket:
        message = json.loads(socket.receive_text())
        assert message["type"] == "genesis" and message["genesis"]["world_id"] == world_id
    wait_for_genesis(api, world_id)


# -- god ---------------------------------------------------------------------


def test_god_command_returns_a_verdict_and_changes_the_world(api):
    branch = toy_branch(api)
    killed = api.post(f"/api/branches/{branch}/god", json={"text": "kill Otto Brandt"}).json()
    assert killed["verdict"] == "apply" and killed["event_seqs"]
    state = api.get(f"/api/branches/{branch}/state").json()
    assert state["entities"][toy.OTTO]["alive"] is False

    again = api.post(f"/api/branches/{branch}/god", json={"text": "kill Otto Brandt"}).json()
    assert again["verdict"] == "reject" and again["explanation"] == "Otto Brandt is already dead."

    born = api.post(f"/api/branches/{branch}/god", json={"text": "Albert Einstein is born at a house in town"}).json()
    assert born["verdict"] == "apply_adjusted"
    assert "a home was created: Einstein House" in born["explanation"]
    assert "not anyone from real history" in born["explanation"]
    assert api.post(f"/api/branches/{branch}/god", json={"text": " "}).status_code == 422

    history = api.get(f"/api/branches/{branch}/chronicle").json()
    entries = [e["narration"] for year in history for e in year["entries"]]
    assert entries == ["Otto Brandt dies.", "A child, Albert Einstein, is born."]


def test_the_gods_touch_promotes_and_witnesses_remember(api):
    branch = toy_branch(api)
    hub = api.app.state.hub
    runner = hub.runner(branch)
    api.post(f"/api/branches/{branch}/god", json={"text": "set rule x = 1"})
    from tinyworld.core import effects as fx
    from tinyworld.core.events import EventDraft

    runner.session.commit([EventDraft(actor="system", effects=[fx.SetAttr(entity=toy.LENA, key="tier", value=1)])])
    moved = api.post(f"/api/branches/{branch}/god", json={"text": "move Lena Vogel to Market Square"}).json()
    assert moved["verdict"] == "apply"
    assert runner.session.state.entities[toy.LENA].attrs["tier"] == 0
    assert any("suddenly at Market Square" in m.text for m in runner.sim.memory.list(branch, toy.LENA))


def test_retroactive_god_command_forks_on_confirmation(api):
    branch = toy_branch(api)
    for _ in range(4):
        api.post(f"/api/branches/{branch}/run", json={"action": "step"})
    hub = api.app.state.hub
    from tinyworld.god.parser import GodCommand

    runner = hub.runner(branch)
    import asyncio

    result = asyncio.run(
        runner.god.apply(runner.session, "kill Otto last morning", [GodCommand(op="remove", target=toy.OTTO, when="1943-03-14T09:00")])
    )
    assert result.verdict == "needs_fork"
    confirmed = api.post(f"/api/branches/{branch}/god/fork", json=result.model_dump(mode="json")).json()
    fork = confirmed["branch_id"]
    assert confirmed["result"]["verdict"] == "apply"
    assert api.get(f"/api/branches/{fork}/state").json()["entities"][toy.OTTO]["alive"] is False
    assert api.get(f"/api/branches/{branch}/state").json()["entities"][toy.OTTO]["alive"] is True
    assert api.post(f"/api/branches/{branch}/god/fork", json=confirmed["result"]).status_code == 422


# -- time, forks and history -------------------------------------------------


def test_skip_fork_diff_causes_metrics_and_export(api):
    world_id, branch = new_world(api)
    api.post(f"/api/branches/{branch}/run", json={"action": "step"})
    api.post(f"/api/branches/{branch}/god", json={"text": "kill Ernst Kruger"})
    split = api.get(f"/api/branches/{branch}").json()["head_seq"]

    fork = api.post(f"/api/branches/{branch}/fork", json={"name": "famine"}).json()
    assert fork["fork_seq"] == split
    other = fork["branch_id"]
    api.post(f"/api/branches/{other}/god", json={"text": "A famine strikes the district"})

    skipped = api.post(f"/api/branches/{branch}/skip", json={"span": "3y"}).json()
    assert skipped["complete"] and skipped["periods"] == 37 and skipped["stopped"] is None
    assert skipped["status"]["sim_time"].startswith("1944-09")
    assert len(skipped["summaries"]) == 37
    assert api.post(f"/api/branches/{branch}/skip", json={"span": "soon"}).status_code == 422
    assert api.post(f"/api/branches/{branch}/skip", json={}).status_code == 422
    assert api.post(f"/api/branches/{branch}/fork", json={"at_seq": 999999}).status_code == 422

    tree = {b["name"]: b for b in api.get(f"/api/worlds/{world_id}").json()["branches"]}
    assert tree["famine"]["parent_id"] == branch and tree["famine"]["fork_seq"] == split

    diff = api.get(f"/api/branches/{branch}/diff/{other}").json()
    assert diff["split_seq"] == split
    assert diff["b"]["events"][0]["narration"] == "A famine strikes the district."
    assert len(diff["a"]["events"]) > 0
    assert diff["a"]["sim_time"] > diff["b"]["sim_time"]

    chronicle = api.get(f"/api/branches/{branch}/chronicle").json()
    assert [year["year"] for year in chronicle] == [1941, 1942, 1943, 1944]
    kinds = {entry["kind"] for year in chronicle for entry in year["entries"]}
    assert kinds >= {"god", "period", "chronicle"}

    chronicled = api.get(f"/api/branches/{branch}/events", params={"kind": "chronicle", "newest": True, "limit": 50}).json()
    with_causes = next(e for e in chronicled if e["causes"])
    graph = api.get(f"/api/branches/{branch}/causes/{with_causes['seq']}").json()
    assert graph["root"] == with_causes["seq"] and len(graph["nodes"]) >= 2
    assert all(edge["from"] < edge["to"] for edge in graph["edges"])
    assert {edge["why"] for edge in graph["edges"]} <= {"prompted", "undertaking", "origin"}
    assert api.get(f"/api/branches/{branch}/causes/999999").json()["nodes"] == []

    metrics = api.get(f"/api/branches/{branch}/metrics").json()
    assert metrics["population"] == {"alive": 9, "dead": 1, "by_tier": {"0": 9}, "background": 4000}
    assert metrics["simulated_years"] == pytest.approx(3.0, abs=0.01)
    assert metrics["cost"]["per_simulated_year"] == pytest.approx(metrics["cost"]["total"] / 3.0, rel=0.01)
    assert {g["name"] for g in metrics["groups"]} >= {"Party Local Group", "Town Council"}
    assert any(r["name"] == "grain" and r["total"] == 134 for r in metrics["resources"])

    exported = api.get(f"/api/branches/{branch}/export").json()
    assert exported["world"]["premise"] == berlin.PREMISE_TEXT
    assert exported["bible"]["premise"]["start_date"] == "1941-09-15"
    assert len(exported["events"]) == api.get(f"/api/branches/{branch}").json()["head_seq"]
    assert exported["chronicle"] == chronicle

    past = api.get(f"/api/branches/{branch}/state", params={"seq": split}).json()
    assert past["sim_time"].startswith("1941-09-15")
    assert api.get(f"/api/branches/{branch}/state", params={"seq": 999999}).status_code == 404


def test_worlds_persist_across_a_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from tinyworld.core.store import Store

    path = str(tmp_path / "worlds.sqlite")
    with TestClient(create_app(Hub(Store(path)))) as first:
        world_id, branch = new_world(first)
        for _ in range(3):
            first.post(f"/api/branches/{branch}/run", json={"action": "step"})
        before = first.get(f"/api/branches/{branch}/state").json()
        memories = first.get(f"/api/branches/{branch}/agents/person:anna_keller").json()["memories"]["count"]
        first.app.state.hub.store.close()

    with TestClient(create_app(Hub(Store(path)))) as second:
        assert second.get(f"/api/worlds/{world_id}").json()["genesis"]["stage"] == "done"
        assert second.get(f"/api/branches/{branch}/state").json() == before
        anna = second.get(f"/api/branches/{branch}/agents/person:anna_keller").json()
        assert anna["memories"]["count"] == memories and anna["thought"]
        assert second.post(f"/api/branches/{branch}/run", json={"action": "step"}).json()["status"]["seq"] > before["seq"]
