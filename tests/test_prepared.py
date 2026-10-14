import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from tinyworld.api.app import create_app
from tinyworld.api.hub import Hub
from tinyworld.core.store import Store
from tinyworld.eval import invariants
from tinyworld.fixtures import berlin, lucknow, prepared
from tinyworld.genesis import critic
from tinyworld.genesis.pipeline import GenesisPipeline
from tinyworld.genesis.seeding import check_world
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import LLMFatal, LLMResult
from tinyworld.sim.loop import Simulation
from test_api import wait_for_genesis

KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "TINYWORLD_PROVIDER")


@pytest.fixture
def api(monkeypatch):
    for name in KEYS:
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(Hub())) as client:
        yield client


def build(module):
    store = Store()
    config = LLMConfig()
    genesis = GenesisPipeline(
        store, StructuredLLM(FakeLLM(module.genesis_handlers()), config, Tracer(store, config))
    )
    world = genesis.create_world(module.PREMISE_TEXT)
    asyncio.run(genesis.run(world))
    return genesis, world


def test_the_premise_picks_the_prepared_world_that_fits():
    assert prepared.pick("What if India never had Jio in 2016. Lucknow.")[0] == "lucknow"
    assert prepared.pick("no jio internet, a city in uttar pradesh")[0] == "lucknow"
    key, _, matched = prepared.pick("1941 Germany never invades the USSR, a town near Berlin")
    assert key == "berlin" and matched
    key, _, matched = prepared.pick("A medieval monastery under siege")
    assert key == "berlin" and not matched


def test_the_lucknow_bible_has_no_findings_that_would_block_a_run():
    genesis, world = build(lucknow)
    bible = genesis.bibles.load(world)
    blocking = [f for f in critic.check(bible) if f.blocking]
    assert blocking == [], blocking
    assert len(bible.figures.figures) >= 8
    for figure in bible.figures.figures:
        assert figure.goals and figure.fears, figure.name
    assert bible.technology.dependencies


def test_the_lucknow_world_seeds_and_runs_without_breaking_an_invariant():
    genesis, world = build(lucknow)
    session = genesis.seed(world)[0]
    assert check_world(session.state) == []
    assert len(session.state.people()) >= 8
    assert "idea:cheap_4g_data_plans" in session.state.rules["knowledge"]
    fake = offline_llm(lambda: session.state, seed="lucknow")
    config = LLMConfig()
    sim = Simulation(session, StructuredLLM(fake, config, Tracer(session.store, config)))
    asyncio.run(sim.run(10))
    assert invariants.check_log(session.store, session.branch_id) == []


def test_every_person_in_the_prepared_worlds_is_invented_not_named_after_the_famous():
    # A guard against drifting back to real, living public figures.
    famous = {"mittal", "ambani", "modi", "kant", "adani", "yogi", "kejriwal"}
    genesis, world = build(lucknow)
    for figure in genesis.bibles.load(world).figures.figures:
        assert not famous & set(figure.name.lower().split()), figure.name


def test_offline_genesis_builds_the_world_that_matches_what_was_typed(api):
    world_id = api.post(
        "/api/worlds", json={"premise": "India never got Jio in 2016. Lucknow."}
    ).json()["world_id"]
    world = wait_for_genesis(api, world_id)
    assert world["prepared"] == {
        "key": "lucknow", "label": lucknow.LABEL, "matched": True,
    }
    bible = api.get(f"/api/worlds/{world_id}/bible").json()["bible"]
    names = {f["name"] for f in bible["figures"]["figures"]}
    assert "Asha Devi" in names and "Anna Keller" not in names


def test_an_unmatched_premise_says_it_is_not_built_from_the_text(api):
    world_id = api.post("/api/worlds", json={"premise": "A monastery under siege."}).json()["world_id"]
    world = wait_for_genesis(api, world_id)
    assert world["offline"] is True
    assert world["prepared"]["matched"] is False
    assert world["prepared"]["key"] == "berlin"


class AnswerOK:
    constrained = False

    async def complete(self, request, model, effort):
        return LLMResult(text='{"ok": true}', model=model, input_tokens=1, output_tokens=1)


class RejectKey:
    async def complete(self, request, model, effort):
        raise LLMFatal("the key was rejected")


def test_a_working_key_switches_the_app_to_a_model_and_is_not_written_anywhere(
    api, monkeypatch, tmp_path
):
    monkeypatch.setattr("tinyworld.api.hub.make_client", lambda provider: AnswerOK())
    secret = "sk-test-not-a-real-key"
    reply = api.post("/api/connect", json={"provider": "openrouter", "key": secret})
    assert reply.status_code == 200
    status = api.get("/api/status").json()
    assert status["model_configured"] is True and status["offline"] is False
    # Only this process holds it.
    assert os.environ.get("OPENROUTER_API_KEY") == secret
    monkeypatch.delenv("OPENROUTER_API_KEY")


def test_a_rejected_key_changes_nothing(api, monkeypatch):
    monkeypatch.setattr("tinyworld.api.hub.make_client", lambda provider: RejectKey())
    reply = api.post("/api/connect", json={"provider": "gemini", "key": "bad"})
    assert reply.status_code == 401
    assert api.get("/api/status").json()["offline"] is True
    assert "GEMINI_API_KEY" not in os.environ


def test_connect_refuses_an_unknown_provider_and_an_empty_key(api):
    assert api.post("/api/connect", json={"provider": "nope", "key": "x"}).status_code == 422
    assert api.post("/api/connect", json={"provider": "openrouter", "key": "  "}).status_code == 422
