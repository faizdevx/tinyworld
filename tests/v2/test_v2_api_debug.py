from fastapi.testclient import TestClient

from tinyworld.api.app import create_app
from tinyworld.api.hub import Hub
from tinyworld.fixtures import toy
from tinyworld.llm.fake import FakeLLM


def client(fake=None):
    return TestClient(create_app(Hub(client=fake)))


def test_debug_page_is_served():
    response = client().get("/debug")
    assert response.status_code == 200
    assert "TinyWorld debug" in response.text


def test_scripted_intents_run_through_the_full_path():
    api = client(FakeLLM())
    branch = api.post("/api/worlds/toy").json()["branch_id"]
    seeded = len(api.get(f"/api/branches/{branch}/events").json())

    response = api.post(
        f"/api/branches/{branch}/intents",
        json={
            "intents": [
                {"agent": toy.ANNA, "verb": "move", "target": toy.SQUARE},
                {"agent": toy.OTTO, "verb": "move", "target": "place:moon"},
                {
                    "agent": toy.LENA,
                    "verb": "speak",
                    "utterance": {"text": "Is anyone there?", "channel": "audible"},
                },
            ]
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert [o["status"] for o in body["outcomes"]] == ["success", "impossible", "success"]
    assert len(body["events"]) == 2
    assert {o["observer"] for o in body["observations"]} >= {toy.ANNA, toy.LENA, toy.OTTO}

    events = api.get(f"/api/branches/{branch}/events", params={"after": seeded}).json()
    assert len(events) == 2
    state = api.get(f"/api/branches/{branch}/state").json()
    assert state["entities"][toy.ANNA]["location"] == toy.SQUARE
    assert state["seq"] == seeded + 2


def test_unknown_branch_is_a_404_and_bad_intents_a_422():
    api = client()
    assert api.get("/api/branches/nope/state").status_code == 404
    branch = api.post("/api/worlds/toy").json()["branch_id"]
    bad = api.post(f"/api/branches/{branch}/intents", json={"intents": [{"agent": toy.ANNA, "verb": "fly"}]})
    assert bad.status_code == 422


def test_status_reports_whether_a_model_is_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert client().get("/api/status").json()["model_configured"] is False
    assert client(FakeLLM()).get("/api/status").json()["model_configured"] is True
