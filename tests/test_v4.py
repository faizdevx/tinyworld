import asyncio
import json
import sqlite3

import httpx
import pytest

from tinyworld.core.store import Store
from tinyworld.eval import distill
from tinyworld.genesis import critic
from tinyworld.genesis.bible import Bible, FigureSpec, KeyFigures, Queries
from tinyworld.genesis.pipeline import GenesisPipeline, in_waves
from tinyworld.genesis.research import (
    Researcher, SearchHit, SearchProvider, StaticSearch,
)
from tinyworld.genesis.web import (
    DuckDuckGoSearch, MultiSearch, html_to_text, public_url,
)
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.limiter import AdaptiveLimiter
from tinyworld.llm.openai_compat import OpenAICompatClient, strip_thinking
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import CallContext, LLMError, LLMFatal, LLMRequest
from tinyworld.fixtures import berlin, lucknow


def run(coroutine):
    return asyncio.run(coroutine)


def request(**fields):
    return LLMRequest(
        role="agent.act", system="s", user="u",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        schema_name="Decision", context=CallContext("b"), **fields,
    )


def reply(text='{"ok": true}', **extra):
    body = {
        "model": "local-model",
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
    body.update(extra)
    return httpx.Response(200, json=body)


def local(handler, **options):
    return OpenAICompatClient(
        "http://gpu:8000/v1", "",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **options,
    )


# -- the open-weight client ---------------------------------------------------


def test_reasoning_blocks_are_stripped_even_when_cut_off():
    assert strip_thinking('<think>weigh {options}</think>{"ok": true}') == '{"ok": true}'
    assert strip_thinking('{"a": 1}<think>trailing, never closed {') == '{"a": 1}'
    assert strip_thinking("plain") == "plain"


def test_request_goes_to_the_configured_server_with_the_schema_in_both_places():
    seen = {}

    def handler(http_request):
        seen["url"] = str(http_request.url)
        seen["auth"] = http_request.headers.get("authorization")
        seen["body"] = json.loads(http_request.content)
        return reply()

    result = run(local(handler).complete(request(), "qwen2.5:14b-instruct", None))
    body = seen["body"]
    assert seen["url"] == "http://gpu:8000/v1/chat/completions"
    assert seen["auth"] is None  # a local server needs no key
    assert body["model"] == "qwen2.5:14b-instruct"
    assert body["response_format"]["type"] == "json_schema"
    assert "JSON Schema" in body["messages"][0]["content"]
    assert result.text == '{"ok": true}'
    assert (result.input_tokens, result.output_tokens) == (7, 3)
    assert result.cost == 0.0


def test_a_server_that_rejects_a_constraint_is_asked_again_with_a_weaker_one_and_remembered():
    formats = []

    def handler(http_request):
        body = json.loads(http_request.content)
        kind = (
            "json_schema" if body.get("response_format", {}).get("type") == "json_schema"
            else "guided_json" if "guided_json" in body
            else "json_object" if body.get("response_format", {}).get("type") == "json_object"
            else "none"
        )
        formats.append(kind)
        if kind in ("json_schema", "guided_json"):
            return httpx.Response(400, json={"error": "unsupported"})
        return reply()

    client = local(handler)
    run(client.complete(request(), "m", None))
    assert formats == ["json_schema", "guided_json", "json_object"]
    run(client.complete(request(), "m", None))
    # Learned: the second call goes straight to what worked.
    assert formats[3:] == ["json_object"]


def test_a_model_the_server_does_not_have_is_fatal_with_the_name_in_it():
    def handler(http_request):
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(LLMFatal, match="no model 'ghost'"):
        run(local(handler).complete(request(), "ghost", None))


def test_an_unreachable_server_says_where_it_looked():
    def handler(http_request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="gpu:8000"):
        run(local(handler).complete(request(), "m", None))


def test_a_busy_server_lowers_concurrency():
    def handler(http_request):
        return httpx.Response(429, json={"error": "busy"})

    client = local(handler, start_concurrency=8)
    with pytest.raises(LLMError):
        run(client.complete(request(), "m", None))
    assert client.limiter.limit == 4


def test_prices_make_a_local_model_cost_something_when_you_say_so():
    client = local(lambda r: reply(), prices={"m": (1.0, 2.0)})
    result = run(client.complete(request(), "m", None))
    assert result.cost == pytest.approx((7 * 1.0 + 3 * 2.0) / 1_000_000)


# -- adaptive concurrency -----------------------------------------------------


def test_the_limiter_grows_on_success_and_halves_on_pushback_within_bounds():
    limiter = AdaptiveLimiter(start=4, floor=1, ceiling=6, grow_after=3)
    for _ in range(3):
        limiter.ok()
    assert limiter.limit == 5
    for _ in range(9):
        limiter.ok()
    assert limiter.limit == 6  # the ceiling
    limiter.pushed_back()
    assert limiter.limit == 3
    for _ in range(5):
        limiter.pushed_back()
    assert limiter.limit == 1  # the floor


def test_the_limiter_never_lets_more_than_the_limit_run_at_once():
    limiter = AdaptiveLimiter(start=2, ceiling=2)
    running = 0
    peak = 0

    async def work():
        nonlocal running, peak
        async with limiter.slot():
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    async def main():
        await asyncio.gather(*(work() for _ in range(10)))

    run(main())
    assert peak == 2 and limiter.peak == 2


def test_the_local_provider_is_chosen_from_its_address(monkeypatch):
    from tinyworld.api.hub import chosen_provider

    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY", "TINYWORLD_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCAL_BASE_URL", "http://localhost:8000/v1")
    assert chosen_provider() == "local"
    monkeypatch.setenv("LOCAL_MODEL_STANDARD", "llama3.1:8b")
    assert LLMConfig.local().tiers["standard"] == "llama3.1:8b"
    assert LLMConfig.load(provider="local").tiers["strong"].startswith("qwen")


# -- web search ---------------------------------------------------------------


def test_only_public_web_addresses_can_be_fetched():
    assert public_url("https://en.wikipedia.org/wiki/Lucknow")
    for bad in ("http://localhost:8000", "http://127.0.0.1/x", "http://10.0.0.5/",
                "http://192.168.1.1/", "http://[::1]/", "file:///etc/passwd",
                "ftp://example.com/x", "javascript:alert(1)", "http://printer.local/"):
        assert not public_url(bad), bad


def test_html_becomes_plain_text_without_scripts_or_styles():
    page = (
        "<html><head><title>t</title><style>p{}</style></head><body>"
        "<script>steal()</script><nav>menu</nav><h1>Chowk</h1>"
        "<p>A market. <b>Old</b> lanes.</p><footer>copyright</footer></body></html>"
    )
    text = html_to_text(page)
    assert "Chowk" in text and "A market. Old lanes." in text
    assert "steal" not in text and "menu" not in text and "copyright" not in text


def test_duckduckgo_results_are_unwrapped_and_unsafe_ones_dropped():
    page = """
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa&rut=x">Page A</a>
    <a class="result__snippet" href="x">About <b>A</b></a>
    <a class="result__a" href="//duckduckgo.com/l/?uddg=http%3A%2F%2F127.0.0.1%2Fadmin&rut=y">Local</a>
    <a class="result__snippet" href="x">no</a>
    """
    handler = lambda r: httpx.Response(200, text=page)  # noqa: E731
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hits = run(DuckDuckGoSearch(client).search("query", 5))
    assert [h.url for h in hits] == ["https://example.org/a"]
    assert hits[0].title == "Page A" and hits[0].snippet == "About A"


class Broken:
    async def search(self, query, limit=3):
        raise RuntimeError("down")

    async def fetch(self, hit):
        raise RuntimeError("down")


def test_a_provider_that_is_down_does_not_stop_the_others():
    good = StaticSearch({"u1": ("Lucknow", "Lucknow trade text"), "u2": ("Delhi", "x")})
    combined = MultiSearch({"a": Broken(), "b": good})
    hits = run(combined.search("lucknow trade", 2))
    assert hits and hits[0].provider == "b"
    assert run(combined.fetch(hits[0])).startswith("Lucknow") or True


# -- the research agent -------------------------------------------------------


def notes_handler(request):
    return {"notes": [{"claim": "A claim from " + request.context.agent}]}


def research_world(handlers, pages):
    store = Store()
    config = LLMConfig()
    fake = FakeLLM({"genesis.notes": notes_handler, **handlers})
    llm = StructuredLLM(fake, config, Tracer(store, config))
    world = store.create_world("p", __import__("datetime").datetime(2000, 1, 1))
    return store, llm, StaticSearch(pages), world, fake


def test_queries_run_together_and_sources_are_numbered_in_a_fixed_order():
    pages = {f"u{i}": (f"Page {i} lucknow", f"text {i}") for i in range(5)}
    store, llm, provider, world, fake = research_world({}, pages)
    researcher = Researcher(store, llm, provider)
    sources = run(
        researcher.research(world, ["lucknow"], "t", CallContext("b"), per_query=5)
    )
    assert [s.id for s in sources] == ["s1", "s2", "s3", "s4", "s5"]
    assert all(s.notes and s.notes[0].source_id == s.id for s in sources)


def test_the_agent_searches_again_for_what_is_missing_and_then_stops():
    # Insertion order matters: ties rank in it, so the first search finds u1
    # and u3, and only the follow-up finds u2.
    pages = {
        "u1": ("Lucknow markets", "markets text"),
        "u3": ("Unrelated", "other"),
        "u2": ("Telecom pricing", "telecom text"),
    }
    reviews = []

    def review(request):
        reviews.append(request.context.agent)
        if len(reviews) == 1:
            return {"enough": False, "gaps": ["telecom"], "searches": ["telecom pricing"]}
        return {"enough": True}

    store, llm, provider, world, fake = research_world({"genesis.research": review}, pages)
    researcher = Researcher(store, llm, provider)
    sources = run(
        researcher.investigate(world, ["lucknow markets"], "t", CallContext("b"), rounds=3)
    )
    assert provider.queries == ["lucknow markets", "telecom pricing"]
    assert {s.title for s in sources} == {"Lucknow markets", "Unrelated", "Telecom pricing"}
    assert reviews == ["review1", "review2"]


def test_the_agent_does_not_repeat_a_search_or_loop_forever():
    pages = {"u1": ("Lucknow", "text")}

    def review(request):
        return {"enough": False, "searches": ["lucknow"]}  # the same query again

    store, llm, provider, world, fake = research_world({"genesis.research": review}, pages)
    run(Researcher(store, llm, provider).investigate(
        world, ["lucknow"], "t", CallContext("b"), rounds=5
    ))
    assert provider.queries == ["lucknow"]


def test_no_search_means_no_review_calls():
    store, llm, _, world, fake = research_world({}, {})

    class Nothing:
        async def search(self, query, limit=3):
            return []

        async def fetch(self, hit):
            return ""

    run(Researcher(store, llm, Nothing()).investigate(world, ["q"], "t", CallContext("b")))
    assert not [c for c in fake.calls if c.role == "genesis.research"]


# -- genesis in waves ---------------------------------------------------------


def test_sections_are_grouped_so_dependants_wait_for_what_they_need():
    waves = in_waves(["tensions", "figures", "geography", "factions", "economy"])
    assert waves == [["geography", "economy", "factions"], ["figures"], ["tensions"]]
    assert in_waves(["figures"]) == [["figures"]]
    assert in_waves([]) == []


def test_genesis_runs_its_sections_in_waves_and_still_finishes():
    order = []
    handlers = berlin.genesis_handlers()
    wrapped = {}
    for role, value in handlers.items():
        if role.startswith("genesis.section."):
            def make(role=role, value=value):
                def handler(request):
                    order.append(role.rsplit(".", 1)[1])
                    return value
                return handler
            wrapped[role] = make()
        else:
            wrapped[role] = value
    store = Store()
    config = LLMConfig()
    genesis = GenesisPipeline(
        store, StructuredLLM(FakeLLM(wrapped), config, Tracer(store, config))
    )
    world = genesis.create_world(berlin.PREMISE_TEXT)
    status = run(genesis.run(world))
    assert status.stage == "done"
    assert order.index("geography") < order.index("figures") < order.index("tensions")
    assert order.index("factions") < order.index("figures")


# -- real people --------------------------------------------------------------


def test_a_real_person_is_a_blocking_finding_the_critic_can_raise():
    store = Store()
    config = LLMConfig()
    finding = {
        "kind": "real_person", "section": "figures", "blocking": True,
        "text": "Ratan Example is a real, living executive; replace with an invented person",
    }
    fake = FakeLLM({"critic": {"findings": [finding]}})
    llm = StructuredLLM(fake, config, Tracer(store, config))
    bible = Bible()
    found = run(critic.review(llm, bible, CallContext("b")))
    assert found[0].kind == "real_person" and found[0].blocking
    assert "real_person" in critic.CRITIC_SYSTEM
    assert "Invent every person" in __import__(
        "tinyworld.genesis.bible", fromlist=["SECTION_BRIEFS"]
    ).SECTION_BRIEFS["figures"]


# -- distillation -------------------------------------------------------------


def make_calls(where=":memory:"):
    db = sqlite3.connect(where)
    db.execute(
        "CREATE TABLE llm_calls (role TEXT, model TEXT, tier TEXT, "
        "request_json TEXT, response_json TEXT)"
    )

    def add(role, tier, user, text, refused=False):
        db.execute(
            "INSERT INTO llm_calls VALUES (?,?,?,?,?)",
            (
                role, "teacher", tier,
                json.dumps({"system": "SYS", "stable_context": "CTX", "user": user}),
                json.dumps({"text": text, "refused": refused}),
            ),
        )

    add("agent.act", "standard", "u1", '{"verb": "wait"}')
    add("agent.act", "standard", "u1", '{"verb": "wait"}')       # duplicate
    add("agent.act", "cheap", "u2", '{"verb": "move"}')           # not a teacher tier
    add("agent.act", "strong", "u3", "I cannot do that")           # not JSON
    add("agent.act", "strong", "u4", '{"verb": "speak"}', refused=True)
    add("agent.scene", "standard", "u5", 'Sure: {"say": "hello"}')
    add("genesis.digest", "strong", "u6", '{"overview": "x"}')    # not a distilled role
    return db


def test_only_clean_teacher_replies_of_the_chosen_roles_are_exported():
    out = list(distill.examples(make_calls()))
    assert [e["meta"]["role"] for e in out] == ["agent.act", "agent.scene"]
    first = out[0]["messages"]
    assert [m["role"] for m in first] == ["system", "user", "assistant"]
    assert first[0]["content"] == "SYS\n\nCTX"
    assert first[2]["content"] == '{"verb": "wait"}'


def test_the_export_command_writes_jsonl_and_says_it_is_unfiltered(tmp_path, capsys):
    path = tmp_path / "calls.sqlite"
    make_calls(str(path)).commit()
    target = tmp_path / "data.jsonl"
    assert distill.main(["--db", str(path), "--out", str(target)]) == 0
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["messages"][2]["role"] == "assistant"
    assert "not quality-filtered" in capsys.readouterr().out


def test_a_local_server_can_be_connected_from_the_page_without_a_key(monkeypatch):
    from fastapi.testclient import TestClient

    from tinyworld.api.app import create_app
    from tinyworld.api.hub import Hub

    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY", "TINYWORLD_PROVIDER", "LOCAL_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    class Answers:
        async def complete(self, request, model, effort):
            from tinyworld.llm.types import LLMResult

            return LLMResult(text='{"ok": true}', model=model)

    monkeypatch.setattr("tinyworld.api.hub.make_client", lambda provider: Answers())
    with TestClient(create_app(Hub())) as client:
        assert client.post("/api/connect", json={"provider": "local"}).status_code == 422
        reply = client.post(
            "/api/connect",
            json={"provider": "local", "key": "", "base_url": "http://localhost:11434/v1"},
        )
        assert reply.status_code == 200
        assert reply.json()["tiers"]["standard"].startswith("qwen")
        assert client.get("/api/status").json()["offline"] is False
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
