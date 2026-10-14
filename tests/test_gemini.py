import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel

from tinyworld.api.hub import Hub, chosen_provider
from tinyworld.core.store import Store
from tinyworld.llm import smoke
from tinyworld.llm.gemini import THINKING_HEADROOM, GeminiClient
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import CallContext, LLMError, LLMRequest


def run(coroutine):
    return asyncio.run(coroutine)


class Move(BaseModel):
    to: str
    why: str = ""


def request(**kwargs):
    return LLMRequest(
        role="agent.act", system="Decide.", stable_context="A small town.",
        user="Where to?", schema=Move.model_json_schema(), max_tokens=500, **kwargs,
    )


def reply(text='{"to": "place:tavern"}', **extra):
    body = {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 9, "thoughtsTokenCount": 30},
        "modelVersion": "gemini-test-001",
    }
    body.update(extra)
    return httpx.Response(200, json=body)


def client_for(handler, **options):
    transport = httpx.MockTransport(handler)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    gemini = GeminiClient(
        "test-key", http=httpx.AsyncClient(transport=transport), sleep=sleep, **options
    )
    return gemini, sleeps


def test_request_shape_and_parsed_reply():
    seen = {}

    def handler(http_request):
        seen["url"] = str(http_request.url)
        seen["key"] = http_request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(http_request.content)
        return reply()

    gemini, _ = client_for(handler)
    result = run(gemini.complete(request(), "gemini-2.5-flash", "low"))

    assert seen["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert "test-key" not in seen["url"] and seen["key"] == "test-key"
    body = seen["body"]
    system = body["systemInstruction"]["parts"][0]["text"]
    assert system.startswith("Decide.") and "A small town." in system
    assert '"to"' in system  # the schema is in the prompt as well
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Where to?"}]}]
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["maxOutputTokens"] == 500 + THINKING_HEADROOM
    assert config["responseJsonSchema"]["required"] == ["to", "why"]

    assert result.text == '{"to": "place:tavern"}'
    assert (result.input_tokens, result.output_tokens) == (40, 39)  # reasoning counts as output
    assert result.model == "gemini-test-001" and not result.refused


def test_thinking_parts_are_not_part_of_the_answer():
    body = {
        "candidates": [{"content": {"parts": [
            {"text": "Let me think about the town.", "thought": True},
            {"text": '{"to": "x"}'},
        ]}, "finishReason": "STOP"}],
    }
    gemini, _ = client_for(lambda r: httpx.Response(200, json=body))
    assert run(gemini.complete(request(), "m", None)).text == '{"to": "x"}'


def test_a_rejected_schema_is_retried_without_it():
    bodies = []

    def handler(http_request):
        body = json.loads(http_request.content)
        bodies.append(body)
        if "responseJsonSchema" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "bad schema"}})
        return reply()

    gemini, _ = client_for(handler)
    result = run(gemini.complete(request(), "m", None))
    assert result.text == '{"to": "place:tavern"}'
    assert len(bodies) == 2 and "responseJsonSchema" not in bodies[1]["generationConfig"]


def test_rate_limits_are_retried_with_backoff_then_reported():
    calls = []

    def handler(http_request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "slow down"}})

    gemini, sleeps = client_for(handler, retries=2, backoff=1.0)
    with pytest.raises(LLMError, match="RESOURCE_EXHAUSTED: slow down"):
        run(gemini.complete(request(), "m", None))
    assert len(calls) == 3 and sleeps == [1.0, 2.0]


def test_the_servers_retry_delay_is_honoured():
    state = {"n": 0}

    def handler(http_request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, json={"error": {
                "status": "RESOURCE_EXHAUSTED", "message": "quota",
                "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "23s"}],
            }})
        if state["n"] == 2:
            return httpx.Response(429, json={"error": {"message": "Please retry in 7.5s."}})
        return reply()

    gemini, sleeps = client_for(handler, backoff=1.0)
    assert run(gemini.complete(request(), "m", None)).text
    assert sleeps == [23.0, 7.5]


def test_requests_per_minute_are_paced():
    now = {"t": 0.0}
    waits = []

    async def sleep(seconds):
        waits.append(round(seconds, 2))
        now["t"] += seconds

    gemini = GeminiClient(
        "k", http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: reply())),
        sleep=sleep, requests_per_minute=2, clock=lambda: now["t"],
    )

    async def burst():
        await asyncio.gather(*(gemini.complete(request(), "m", None) for _ in range(3)))

    run(burst())
    assert waits == [60.05]  # the third waits for the first to age out


def test_concurrency_is_capped():
    active = {"now": 0, "peak": 0}

    class Slow(httpx.AsyncBaseTransport):
        async def handle_async_request(self, http_request):
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
            await asyncio.sleep(0.01)
            active["now"] -= 1
            return reply()

    gemini = GeminiClient("k", http=httpx.AsyncClient(transport=Slow()), max_concurrent=2)

    async def burst():
        await asyncio.gather(*(gemini.complete(request(), "m", None) for _ in range(6)))

    run(burst())
    assert active["peak"] == 2


def test_a_transient_failure_then_success():
    state = {"n": 0}

    def handler(http_request):
        state["n"] += 1
        return httpx.Response(503, text="busy") if state["n"] == 1 else reply()

    gemini, sleeps = client_for(handler)
    assert run(gemini.complete(request(), "m", None)).text
    assert len(sleeps) == 1


def test_auth_and_network_errors_become_llm_errors():
    gemini, _ = client_for(lambda r: httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": "key invalid"}}))
    with pytest.raises(LLMError, match="PERMISSION_DENIED: key invalid"):
        run(gemini.complete(request(), "m", None))

    def boom(http_request):
        raise httpx.ConnectError("no route")

    gemini, _ = client_for(boom)
    with pytest.raises(LLMError, match="connection error"):
        run(gemini.complete(request(), "m", None))


def test_blocked_prompts_and_safety_stops_count_as_refusals():
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 5}}
    gemini, _ = client_for(lambda r: httpx.Response(200, json=blocked))
    assert run(gemini.complete(request(), "m", None)).refused

    stopped = {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}
    gemini, _ = client_for(lambda r: httpx.Response(200, json=stopped))
    assert run(gemini.complete(request(), "m", None)).refused


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiClient()


def test_works_through_structured_calls_including_repair():
    state = {"n": 0}

    def handler(http_request):
        state["n"] += 1
        return reply("Probably the tavern.") if state["n"] == 1 else reply('```json\n{"to": "place:tavern"}\n```')

    gemini, _ = client_for(handler)
    store = Store()
    config = LLMConfig.gemini()
    llm = StructuredLLM(gemini, config, Tracer(store, config))
    result = run(llm.call(
        "agent.act", Move, system="Decide.", user="Where?",
        context=CallContext("b", 1, "p"), fallback=Move(to="nowhere"),
    ))
    assert result.ok and result.attempts == 2 and result.value.to == "place:tavern"
    rows = store.query("SELECT model, tier FROM llm_calls")
    assert [r["tier"] for r in rows] == ["standard", "standard"]
    assert rows[0]["model"] == "gemini-test-001"


def test_list_models_keeps_only_generation_models():
    body = {"models": [
        {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash",
         "inputTokenLimit": 1048576, "outputTokenLimit": 65536,
         "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
    ]}
    gemini, _ = client_for(lambda r: httpx.Response(200, json=body))
    assert run(gemini.list_models()) == [
        {"id": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash",
         "input_limit": 1048576, "output_limit": 65536}
    ]


# -- provider selection ------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY",
                 "GOOGLE_API_KEY", "TINYWORLD_PROVIDER", "GEMINI_MODEL_STRONG"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_provider_follows_the_keys_that_are_set(clean_env):
    assert chosen_provider() is None
    clean_env.setenv("GEMINI_API_KEY", "k")
    assert chosen_provider() == "gemini"
    clean_env.setenv("ANTHROPIC_API_KEY", "k")
    assert chosen_provider() == "anthropic"
    clean_env.setenv("TINYWORLD_PROVIDER", "gemini")
    assert chosen_provider() == "gemini"


def test_hub_uses_gemini_models_and_reports_no_prices(clean_env):
    clean_env.setenv("GEMINI_API_KEY", "k")
    clean_env.setenv("GEMINI_MODEL_STRONG", "gemini-custom")
    hub = Hub(Store())
    assert isinstance(hub.client, GeminiClient) and hub.has_model and not hub.offline
    assert hub.config.route("genesis.premise").model == "gemini-custom"
    assert hub.config.route("agent.act").model == "gemini-2.5-flash"
    assert hub.config.route("memory.importance").model == "gemini-3.5-flash-lite"
    assert hub.config.cost("gemini-2.5-flash", 1_000_000, 1_000_000) == 0.0


def test_hub_without_any_key_stays_offline(clean_env):
    hub = Hub(Store())
    assert hub.client is None and hub.offline


# -- the smoke command -------------------------------------------------------


def test_smoke_steps_run_end_to_end_against_a_scripted_model():
    from tinyworld.fixtures import berlin, toy
    from tinyworld.llm.offline import offline_llm

    session = toy.build_toy()
    fake = offline_llm(lambda: session.state)
    fake.on("smoke.free", {"answer": "A 1939 non-aggression treaty between Germany and the USSR."})
    fake.on("genesis.premise", berlin.PREMISE)
    config = LLMConfig()
    llm = StructuredLLM(fake, config, Tracer(session.store, config))

    results = run(smoke.run_steps(llm, session, smoke.STEPS, "What was the pact?", berlin.PREMISE_TEXT))
    by_step = {r.step: r for r in results}
    assert all(r.ok for r in results), [(r.step, r.detail) for r in results if not r.ok]
    assert "non-aggression treaty" in by_step["prompt"].detail
    assert by_step["agent"].calls == 3 and "Anna Keller:" in by_step["agent"].detail
    assert by_step["genesis"].detail.startswith("1941-09-15")
    assert all(r.repairs == 0 for r in results)


def test_smoke_reports_a_model_that_never_gives_valid_output():
    from tinyworld.fixtures import toy
    from tinyworld.llm.fake import FakeLLM

    session = toy.build_toy()
    config = LLMConfig()
    llm = StructuredLLM(FakeLLM({"*": "I am not going to answer in JSON."}), config, Tracer(session.store, config))
    results = run(smoke.run_steps(llm, session, ["prompt", "agent"], "hi", "x"))
    assert [r.ok for r in results] == [False, False]
    assert results[0].repairs == 2 and "no valid reply" in results[0].detail


def test_smoke_main_explains_a_missing_key(clean_env, capsys, tmp_path):
    clean_env.chdir(tmp_path)
    assert run(smoke.main([])) == 2
    assert "No API key found" in capsys.readouterr().out


def test_auth_failures_are_fatal_not_retried():
    from tinyworld.llm.types import LLMFatal

    calls = []

    def handler(http_request):
        calls.append(1)
        return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED", "message": "key expired"}})

    gemini, sleeps = client_for(handler)
    with pytest.raises(LLMFatal):
        run(gemini.complete(request(), "m", None))
    assert len(calls) == 1 and sleeps == []
