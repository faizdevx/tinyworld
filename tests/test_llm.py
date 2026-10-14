import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.fixtures import toy
from tinyworld.llm import embed, ledger
from tinyworld.llm.client import AnthropicClient, provider_schema
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM, extract_json
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.llm.types import CallContext, LLMError, LLMRequest


def run(coroutine):
    return asyncio.run(coroutine)


class Move(BaseModel):
    to: str = Field(min_length=1)
    why: str = ""


FALLBACK = Move(to="nowhere", why="fallback")
CTX = CallContext("b1", 3, "person:anna_keller")


def structured(fake, store=None):
    config = LLMConfig()
    tracer = Tracer(store, config) if store is not None else None
    return StructuredLLM(fake, config, tracer)


def call(llm, **kwargs):
    options = dict(system="You decide.", user="Where to?", context=CTX, fallback=FALLBACK)
    options.update(kwargs)
    return run(llm.call("agent.act", Move, **options))


# -- router ------------------------------------------------------------------


def test_roles_route_to_tiers_by_longest_prefix():
    config = LLMConfig()
    assert config.route("genesis.bible").tier == "strong"
    assert config.route("agent.act").tier == "standard"
    assert config.route("agent.act.tier1").tier == "cheap"
    assert config.route("memory.importance").tier == "cheap"
    assert config.route("something.new").tier == "standard"
    assert config.route("god.parse").model == config.tiers["strong"]


def test_cost_uses_the_price_table():
    config = LLMConfig()
    model = config.tiers["standard"]
    price = config.prices[model]
    cost = config.cost(model, 1_000_000, 500_000, cache_read_tokens=2_000_000)
    assert cost == pytest.approx(price.input + price.output / 2 + 2 * price.cache_read)
    assert config.cost("unknown-model", 10, 10) == 0.0


def test_config_file_overrides_defaults(tmp_path):
    path = tmp_path / "llm.json"
    path.write_text('{"tiers": {"cheap": "local-model"}, "roles": {"agent.act": "cheap"}}')
    config = LLMConfig.load(path)
    assert config.route("agent.act").model == "local-model"
    assert config.route("critic").tier == "strong"


# -- structured calls --------------------------------------------------------


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('Sure:\n```json\n{"to": "x"}\n```') == '{"to": "x"}'
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_valid_reply_is_returned_on_the_first_attempt():
    fake = FakeLLM({"agent.act": {"to": "place:tavern"}})
    result = call(structured(fake))
    assert result.ok and result.attempts == 1
    assert result.value.to == "place:tavern"


def test_invalid_json_triggers_a_repair_with_the_error_attached():
    fake = FakeLLM({"agent.act": ["I think the tavern.", {"to": "place:tavern"}]})
    result = call(structured(fake))
    assert result.ok and result.attempts == 2
    assert "previous reply was rejected" in fake.calls[1].user
    assert fake.calls[1].user.startswith("Where to?")


def test_schema_violation_triggers_a_repair():
    fake = FakeLLM({"agent.act": [{"to": ""}, {"destination": "x"}, {"to": "place:farm"}]})
    result = call(structured(fake))
    assert result.ok and result.attempts == 3
    assert result.value.to == "place:farm"


def test_fallback_after_repairs_are_exhausted():
    fake = FakeLLM({"agent.act": "not json"})
    result = call(structured(fake))
    assert not result.ok
    assert result.value == FALLBACK
    assert result.attempts == 3
    assert result.error


def test_fallback_can_be_built_from_the_error():
    fake = FakeLLM({"agent.act": "not json"})
    result = call(structured(fake), fallback=lambda error: Move(to="x", why=error))
    assert "JSON" in result.value.why


def test_check_can_reject_a_schema_valid_reply():
    fake = FakeLLM({"agent.act": [{"to": "place:moon"}, {"to": "place:tavern"}]})
    result = call(
        structured(fake),
        check=lambda move: None if move.to != "place:moon" else "no such place",
    )
    assert result.ok and result.value.to == "place:tavern"
    assert "no such place" in fake.calls[1].user


def test_provider_errors_never_raise_into_the_caller():
    class Broken:
        async def complete(self, request, model, effort):
            raise LLMError("rate limited")

    class Crashing:
        async def complete(self, request, model, effort):
            raise RuntimeError("boom")

    for client in (Broken(), Crashing()):
        result = call(structured(client))
        assert not result.ok and result.value == FALLBACK


def test_refusal_goes_straight_to_fallback():
    class Refusing:
        calls = 0

        async def complete(self, request, model, effort):
            from tinyworld.llm.types import LLMResult

            Refusing.calls += 1
            return LLMResult(text="", model=model, refused=True)

    result = call(structured(Refusing()))
    assert not result.ok and Refusing.calls == 1


def test_fake_llm_reports_missing_handlers_as_a_failed_call():
    result = call(structured(FakeLLM()))
    assert not result.ok and "no handler" in result.error


# -- trace and ledger --------------------------------------------------------


def test_every_attempt_is_recorded_and_the_ledger_sums_them():
    session = toy.build_toy()
    store, branch = session.store, session.branch_id
    fake = FakeLLM(
        {
            "agent.act": ["bad", {"to": "place:tavern"}],
            "memory.importance": {"to": "x"},
        }
    )
    llm = structured(fake, store)
    ctx = CallContext(branch, session.state.seq, toy.ANNA)
    first = run(llm.call("agent.act", Move, system="s", user="u", context=ctx, fallback=FALLBACK))
    run(llm.call("memory.importance", Move, system="s", user="u", context=ctx, fallback=FALLBACK))

    rows = store.query("SELECT * FROM llm_calls ORDER BY id")
    assert len(rows) == 3
    assert first.trace_id.endswith("|agent.act|person:anna_keller|1")

    usage = ledger.total(store, branch)
    assert usage.calls == 3
    assert usage.input_tokens == sum(r["input_tokens"] for r in rows)
    assert usage.cost == pytest.approx(sum(r["cost"] for r in rows))
    assert usage.cost > 0

    by_role = ledger.by(store, branch, "role")
    assert by_role["agent.act"].calls == 2
    assert ledger.by(store, branch, "tier")["cheap"].calls == 1
    assert ledger.agent_cost(store, branch, toy.ANNA) == pytest.approx(usage.cost)
    with pytest.raises(ValueError):
        ledger.by(store, branch, "id; DROP TABLE llm_calls")


def test_fork_inherits_cost_only_from_before_the_fork():
    session = toy.build_toy()
    store = session.store
    llm = structured(FakeLLM({"*": {"to": "x"}}), store)

    def spend(branch, seq):
        ctx = CallContext(branch, seq, toy.ANNA)
        run(llm.call("agent.act", Move, system="s", user="u", context=ctx, fallback=FALLBACK))

    spend(session.branch_id, 3)
    spend(session.branch_id, 7)
    child = session.fork(7, "child")
    spend(child.branch_id, 7)

    assert ledger.total(store, session.branch_id).calls == 2
    assert ledger.total(store, child.branch_id).calls == 2
    assert ledger.total(store, child.branch_id, own_only=True).calls == 1


# -- replay ------------------------------------------------------------------

PLACES = [toy.SQUARE, toy.TAVERN, toy.BAKERY, toy.TOWN_HALL]


async def little_run(session, client, ticks=4):
    """A tiny simulation: each tick every person asks the model where to go."""
    llm = StructuredLLM(client, LLMConfig(), Tracer(session.store, LLMConfig()))
    for _ in range(ticks):
        tick_seq = session.state.seq
        people = sorted(p.id for p in session.state.people())
        replies = await asyncio.gather(
            *[
                llm.call(
                    "agent.act",
                    Move,
                    system="Pick a place.",
                    user=f"You are {person}.",
                    context=CallContext(session.branch_id, tick_seq, person),
                    fallback=Move(to=toy.SQUARE),
                )
                for person in people
            ]
        )
        session.commit(
            [
                EventDraft(
                    actor=person,
                    effects=[fx.MoveEntity(entity=person, to=reply.value.to)],
                    narration=reply.value.why,
                    trace_id=reply.trace_id,
                )
                for person, reply in zip(people, replies)
            ],
            atomic=False,
        )


def comparable(events):
    return [e.model_dump(exclude={"branch_id", "trace_id"}) for e in events]


def test_recorded_run_replays_offline_to_an_identical_event_log():
    session = toy.build_toy()
    start = session.state.seq
    counter = {"n": 0}

    def wander(request):
        counter["n"] += 1
        if counter["n"] == 5:
            return "garbage that needs a repair"
        return {"to": PLACES[(counter["n"] * 7) % len(PLACES)], "why": f"step {counter['n']}"}

    run(little_run(session, FakeLLM({"agent.act": wander})))
    recorded = session.store.events(session.branch_id, after=start)
    assert len(recorded) == 12

    replay = session.fork(start, "replay")
    run(little_run(replay, ReplayLLM(session.store, session.branch_id)))
    replayed = session.store.events(replay.branch_id, after=start)

    assert comparable(replayed) == comparable(recorded)
    assert replay.state.model_dump(exclude={"seq"}) == session.state.model_dump(exclude={"seq"})


def test_replay_fails_cleanly_when_the_recording_runs_out():
    session = toy.build_toy()
    llm = structured(ReplayLLM(session.store, session.branch_id))
    result = call(llm)
    assert not result.ok and "no recorded call" in result.error


# -- embeddings --------------------------------------------------------------


def test_hash_embedder_is_deterministic_and_ranks_overlap_higher():
    embedder = embed.HashEmbedder()
    vectors = embedder.embed(
        [
            "the mayor is hoarding grain in the town hall",
            "grain hoarded by the mayor",
            "a quiet walk along the river at dusk",
        ]
    )
    assert vectors.shape == (3, embedder.dim)
    assert embed.cosine(vectors[0], vectors[1]) > embed.cosine(vectors[0], vectors[2])
    assert (embedder.embed(["grain"]) == embedder.embed(["grain"])).all()
    assert embed.cosine(vectors[0], vectors[0]) == pytest.approx(1.0, abs=1e-5)


def test_embedding_bytes_round_trip():
    vector = embed.HashEmbedder(32).embed(["bread"])[0]
    assert (embed.from_bytes(embed.to_bytes(vector)) == vector).all()


# -- anthropic client request shaping ----------------------------------------


def test_provider_schema_drops_unsupported_keywords_and_closes_objects():
    schema = provider_schema(Move.model_json_schema())
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["to", "why"]
    assert "minLength" not in schema["properties"]["to"]
    assert "title" not in schema


class _BadRequest(Exception):
    pass


def _client(create):
    client = object.__new__(AnthropicClient)
    client.constrained = True
    client._anthropic = SimpleNamespace(
        BadRequestError=_BadRequest,
        RateLimitError=type("RateLimitError", (Exception,), {}),
        APIStatusError=type("APIStatusError", (Exception,), {}),
        APIConnectionError=type("APIConnectionError", (Exception,), {}),
    )
    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client


def _response(text='{"to": "x"}'):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=11, output_tokens=5,
            cache_read_input_tokens=7, cache_creation_input_tokens=None,
        ),
        model="m",
        stop_reason="end_turn",
    )


def _request():
    return LLMRequest(
        role="agent.act", system="rules", stable_context="world digest",
        user="now", schema=Move.model_json_schema(),
    )


def test_anthropic_client_sends_cached_prefix_schema_and_effort():
    seen = {}

    async def create(**params):
        seen.update(params)
        return _response()

    result = run(_client(create).complete(_request(), "m", "low"))
    assert [b["text"] for b in seen["system"]] == ["rules", "world digest"]
    assert "cache_control" in seen["system"][1] and "cache_control" not in seen["system"][0]
    assert seen["output_config"]["effort"] == "low"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert seen["messages"] == [{"role": "user", "content": "now"}]
    assert "temperature" not in seen and "thinking" not in seen
    assert (result.text, result.input_tokens, result.cache_read_tokens) == ('{"to": "x"}', 11, 7)
    assert result.cache_write_tokens == 0


def test_anthropic_client_retries_without_the_schema_when_it_is_rejected():
    attempts = []

    async def create(**params):
        attempts.append(params.get("output_config"))
        if len(attempts) == 1:
            raise _BadRequest("schema not supported")
        return _response()

    result = run(_client(create).complete(_request(), "m", "low"))
    assert result.text == '{"to": "x"}'
    assert "format" in attempts[0] or attempts[0] is attempts[1]
    assert attempts[1] == {"effort": "low"}
