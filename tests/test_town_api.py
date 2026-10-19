import time

import pytest
from fastapi.testclient import TestClient

from tinyworld.api.app import create_app
from tinyworld.api.hub import Hub
from tinyworld.fixtures import berlin


@pytest.fixture
def api(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("TINYWORLD_SIM_DELAY", "0")
    with TestClient(create_app(Hub())) as client:
        yield client


def seeded(api):
    world_id = api.post("/api/worlds", json={"premise": berlin.PREMISE_TEXT}).json()["world_id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        w = api.get(f"/api/worlds/{world_id}").json()
        if not w["genesis"]["running"] and w["genesis"]["stage"] != "queued":
            break
        time.sleep(0.05)
    return api.post(f"/api/worlds/{world_id}/seed", json={"name": "main"}).json()["branch_id"]


def test_opening_a_branch_lays_it_out_and_shows_who_is_where(api):
    b = seeded(api)
    snap = api.get(f"/api/town/{b}").json()
    assert snap["type"] == "snapshot" and snap["chunks"] and snap["places"]
    placed = [p for p in snap["people"] if p["x"] is not None]
    assert len(placed) == len(snap["people"]) >= 8
    assert snap["holy"] and "unexplored" in snap
    chunk = snap["chunks"][0]
    assert len(chunk["terrain"]) == 1024 and "regions" in chunk
    one = api.get(f"/api/town/{b}/chunk/{chunk['cx']}/{chunk['cy']}").json()
    assert one["key"] == chunk["key"]
    assert api.get(f"/api/town/{b}/chunk/99/99").status_code == 404


def test_running_moves_people_and_the_paper_comes_out(api):
    b = seeded(api)
    before = {p["id"]: (p["x"], p["y"]) for p in api.get(f"/api/town/{b}/people").json()}
    api.post(f"/api/town/{b}/run", json={"minutes": 26 * 60})
    after = {p["id"]: (p["x"], p["y"]) for p in api.get(f"/api/town/{b}/people").json()}
    assert before != after
    papers = api.get(f"/api/town/{b}/papers").json()
    assert papers and papers[0]["headline"] and papers[0]["stories"]


def test_follow_interview_graphs_and_timeline(api):
    b = seeded(api)
    api.post(f"/api/town/{b}/run", json={"minutes": 180})
    who = api.get(f"/api/town/{b}/people").json()[0]["id"]
    f = api.get(f"/api/town/{b}/follow/{who}").json()
    assert f["name"] and "drives" in f and "plan" in f and f["faith"] == 50
    assert api.get(f"/api/town/{b}/follow/person:nobody").status_code == 404
    a = api.post(f"/api/town/{b}/interview", json={"person": who, "question": "How are you?"}).json()
    assert a["answer"] and a["appeared"] is False
    rel = api.get(f"/api/town/{b}/graph/relationships").json()
    assert rel["nodes"] and rel["edges"]
    assert "edges" in api.get(f"/api/town/{b}/graph/rumours").json()
    assert api.get(f"/api/town/{b}/graph/other").status_code == 404
    snap = api.get(f"/api/town/{b}").json()
    t0 = snap["time"]
    frames = api.get(f"/api/town/{b}/timeline", params={"start": "1941-09-15T08:00:00", "end": "1941-09-15T10:00:00", "step": 30}).json()
    assert len(frames) == 5 and frames[0]["people"]
    assert api.get(f"/api/town/{b}/timeline", params={"start": "x", "end": "y"}).status_code == 422


def test_an_interview_changes_nothing_unless_the_god_appears(api):
    b = seeded(api)
    who = api.get(f"/api/town/{b}/people").json()[0]["id"]
    seq = api.get(f"/api/town/{b}").json()["seq"]
    api.post(f"/api/town/{b}/interview", json={"person": who, "question": "What do you fear?"})
    assert api.get(f"/api/town/{b}").json()["seq"] == seq
    api.post(f"/api/town/{b}/interview", json={"person": who, "question": "Do not be afraid.", "appear": True})
    assert api.get(f"/api/town/{b}").json()["seq"] > seq


def test_a_petition_is_listed_and_answered_over_http(api):
    b = seeded(api)
    for _ in range(60):
        api.post(f"/api/town/{b}/run", json={"minutes": 360})
        if api.get(f"/api/town/{b}/petitions").json():
            break
    open_ = api.get(f"/api/town/{b}/petitions").json()
    if not open_:
        pytest.skip("nobody petitioned in this run")
    p = open_[0]
    bad = api.post(f"/api/town/{b}/petitions/{p['id']}/answer", json={"power": "bless"})
    assert bad.status_code == 422
    ok = api.post(f"/api/town/{b}/petitions/{p['id']}/answer", json={"power": "whisper", "text": "Patience."})
    assert ok.status_code == 200
    assert all(x["id"] != p["id"] for x in api.get(f"/api/town/{b}/petitions").json())
    again = api.post(f"/api/town/{b}/petitions/{p['id']}/answer", json={"power": "whisper"})
    assert again.status_code == 409


def test_gods_have_roles_and_the_socket_streams_positions(api):
    b = seeded(api)
    r = api.post(f"/api/town/{b}/gods", json={"id": "d1", "name": "Demi", "role": "demigod"})
    assert r.status_code == 200 and r.json()["points"] == 20
    assert api.post(f"/api/town/{b}/gods", json={"id": "x", "name": "X", "role": "emperor"}).status_code == 422
    assert [g["id"] for g in api.get(f"/api/town/{b}/gods").json()] == ["d1"]
    with api.websocket_connect(f"/ws/town/{b}") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot"
        api.post(f"/api/town/{b}/run", json={"minutes": 20})
        seen = set()
        for _ in range(8):
            seen.add(ws.receive_json()["type"])
            if "position" in seen:
                break
        assert "position" in seen


def test_the_town_view_opens_in_the_app(api):
    page = api.get("/app/index.html")
    assert page.status_code == 200
    assert api.get("/app/js/town.js").status_code == 200


def test_a_scenario_goes_in_and_a_town_comes_out(api):
    import time as _t

    assert api.post("/api/launch", json={"scenario": "hi"}).status_code == 422
    made = api.post("/api/launch", json={"scenario": "A small trading town on the Silk Road, 1250, where the road is closed."})
    assert made.status_code == 200
    world = made.json()["world_id"]
    deadline = _t.time() + 180
    while _t.time() < deadline:
        p = api.get(f"/api/launch/{world}").json()
        if p["stage"] in ("ready", "failed"):
            break
        _t.sleep(0.2)
    assert p["stage"] == "ready", p
    assert p["tasks"] and p["progress"] == 1.0 and "geography" in p["sections"]
    early = api.post(f"/api/launch/{world}/enter")
    assert early.status_code == 200
    branch = early.json()["branch_id"]
    assert api.post(f"/api/launch/{world}/enter").json()["branch_id"] == branch
    snap = api.get(f"/api/town/{branch}").json()
    assert snap["chunks"] and snap["people"]
    assert api.post("/api/launch/nope/enter").status_code == 404
