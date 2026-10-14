import asyncio
import json

import httpx
import pytest

from tinyworld.llm.openrouter import OpenRouterClient
from tinyworld.llm.types import CallContext, LLMError, LLMFatal, LLMRequest


def run(coroutine):
    return asyncio.run(coroutine)


def request():
    return LLMRequest(
        role="genesis.premise", system="s", user="u",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        context=CallContext("b"),
    )


def ok(text='{"ok": true}'):
    return httpx.Response(
        200,
        json={
            "model": "m",
            "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "cost": 0.0001},
        },
    )


def client_for(handler, **options):
    async def sleep(seconds):
        pass

    return OpenRouterClient(
        "test-key", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleep=sleep, reasoning=False, **options,
    )


def test_reasoning_is_off_by_default_and_cost_is_reported():
    seen = {}

    def handler(http_request):
        seen["body"] = json.loads(http_request.content)
        return ok()

    result = run(client_for(handler).complete(request(), "some/model", None))
    assert seen["body"]["reasoning"] == {"enabled": False}
    assert result.cost == pytest.approx(0.0001)


def test_a_model_that_requires_reasoning_is_asked_again_with_it_and_remembered():
    bodies = []

    def handler(http_request):
        body = json.loads(http_request.content)
        bodies.append(body)
        if body.get("reasoning") == {"enabled": False}:
            return httpx.Response(
                400,
                json={"error": {"message": "Reasoning is mandatory for this endpoint and cannot be disabled."}},
            )
        return ok()

    client = client_for(handler)
    first = run(client.complete(request(), "needs/reasoning", None))
    assert first.text == '{"ok": true}'
    assert bodies[-1]["reasoning"] == {"effort": "low"}
    # Room for the hidden thinking on top of the answer.
    assert bodies[-1]["max_tokens"] > bodies[0]["max_tokens"]

    before = len(bodies)
    run(client.complete(request(), "needs/reasoning", None))
    # Learned: no second rejected attempt for the same model.
    assert len(bodies) == before + 1
    assert bodies[-1]["reasoning"] == {"effort": "low"}


def test_a_bad_key_is_fatal_and_other_errors_are_not():
    def unauthorised(http_request):
        return httpx.Response(401, json={"error": {"message": "no auth"}})

    with pytest.raises(LLMFatal):
        run(client_for(unauthorised).complete(request(), "m", None))

    def broken(http_request):
        return httpx.Response(400, json={"error": {"message": "bad"}})

    with pytest.raises(LLMError) as caught:
        run(client_for(broken).complete(request(), "m", None))
    assert not isinstance(caught.value, LLMFatal)


def test_an_unaffordable_request_is_asked_again_for_what_can_be_afforded():
    seen = []

    def handler(http_request):
        body = json.loads(http_request.content)
        seen.append(body["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(
                402, json={"error": {"message": "can only afford 1000"}},
            )
        return ok()

    run(client_for(handler).complete(request(), "m", None))
    assert seen[1] == 1000 - 16
