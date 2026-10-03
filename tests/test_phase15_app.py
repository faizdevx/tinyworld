from fastapi.testclient import TestClient

from WORLD.app import app


client = TestClient(app)


def test_app_serves_frontend_root():
    response = client.get("/")
    assert response.status_code == 200
    text = response.text.lower()
    assert "tinyworld" in text or "god observatory" in text


def test_status_and_world_endpoints_work():
    status = client.get("/api/status")
    assert status.status_code == 200, status.text
    payload = status.json()
    assert "running" in payload
    assert "experiment_id" in payload
    assert payload["population"] >= 1

    world = client.get("/api/world")
    assert world.status_code == 200, world.text
    data = world.json()
    assert data["population"] >= 1
    assert data["environment"]


def test_step_and_intervention_flow_updates_state():
    before = client.get("/api/status").json()
    step = client.post("/api/simulation/step")
    assert step.status_code == 200, step.text

    payload = {
        "operation": "spawn",
        "target": "entity:foreign_army",
        "properties": {"location": "Northern Road", "size": 500},
        "value": None,
        "visibility": "god_only",
    }
    intervention = client.post("/api/interventions", json=payload)
    assert intervention.status_code == 200, intervention.text
    data = intervention.json()
    assert data["success"] is True
    assert data["target"] == "entity:foreign_army"

    world = client.get("/api/world")
    assert world.status_code == 200, world.text
    assert world.json()["population"] >= 1


def test_checkpoint_save_and_load_round_trip():
    save = client.post("/api/checkpoints/save", json={"checkpoint_id": "PHASE15-TEST"})
    assert save.status_code == 200, save.text
    loaded = client.post("/api/checkpoints/load", json={"checkpoint_id": "PHASE15-TEST"})
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert body["checkpoint_id"] == "PHASE15-TEST"
