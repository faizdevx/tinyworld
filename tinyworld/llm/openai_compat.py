"""A client for any OpenAI-compatible server: the way to run open-weight models.

vLLM, Ollama (``/v1``), llama.cpp's server, LM Studio, TGI, a LiteLLM proxy or
OpenAI itself all speak the same chat-completions protocol. Point
``LOCAL_BASE_URL`` at one and name the model for each tier.

Open-weight models differ from hosted ones in ways that matter here:

- They are often small, so the schema is asked for as strictly as the server
  allows (``json_schema``, then vLLM's ``guided_json``, then ``json_object``),
  and the application still validates and repairs the reply.
- Reasoning models write ``<think>...</think>`` before the answer. That is
  stripped, since it can contain braces that are not the answer.
- A local server has no published rate limit, so concurrency adapts: it grows
  while requests succeed and halves when the server pushes back.
"""

import json
import os
import re
import time

import httpx

from tinyworld.llm.client import provider_schema
from tinyworld.llm.limiter import AdaptiveLimiter
from tinyworld.llm.types import LLMError, LLMFatal, LLMRequest, LLMResult

DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Remove reasoning blocks, including one that was cut off before closing."""
    text = _THINK.sub("", text)
    return _THINK_OPEN.sub("", text).strip()


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 600.0,
        start_concurrency: int | None = None,
        max_concurrency: int | None = None,
        grammar: str | None = None,
        prices: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("LOCAL_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        key = api_key if api_key is not None else os.environ.get("LOCAL_API_KEY", "")
        self._headers = {"Content-Type": "application/json"}
        if key:
            self._headers["Authorization"] = f"Bearer {key}"
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self.limiter = AdaptiveLimiter(
            start=start_concurrency or int(os.environ.get("LOCAL_CONCURRENCY", "4")),
            ceiling=max_concurrency or int(os.environ.get("LOCAL_MAX_CONCURRENCY", "32")),
        )
        # "json_schema" (OpenAI, vLLM, recent Ollama), "guided_json" (older vLLM)
        # or "json_object". Learned from the server if the first choice fails.
        self.grammar = grammar or os.environ.get("LOCAL_GRAMMAR", "json_schema")
        # Local inference is free at the margin; set prices to make budgets bite.
        # model -> (dollars per million input tokens, per million output tokens)
        self.prices = prices or {}
        self._formats = ["json_schema", "guided_json", "json_object", "none"]

    def _body(self, request: LLMRequest, model: str, fmt: str) -> dict:
        system = request.system
        if request.stable_context:
            system += "\n\n" + request.stable_context
        # The schema is also in the prompt: small models follow a described
        # shape far better than an unexplained constraint.
        system += "\n\nThe JSON object must match this JSON Schema:\n" + json.dumps(
            request.schema, separators=(",", ":")
        )
        body: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": request.max_tokens,
            "temperature": 0.7,
        }
        schema = provider_schema(request.schema)
        if fmt == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name or "response",
                    "strict": False,
                    "schema": schema,
                },
            }
        elif fmt == "guided_json":
            body["guided_json"] = schema
        elif fmt == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        started = time.monotonic()
        position = self._formats.index(self.grammar) if self.grammar in self._formats else 0
        response: httpx.Response | None = None
        async with self.limiter.slot():
            while True:
                body = self._body(request, model, self._formats[position])
                try:
                    response = await self._http.post(
                        f"{self.base_url}/chat/completions", headers=self._headers, json=body
                    )
                except httpx.TimeoutException as exc:
                    self.limiter.pushed_back()
                    raise LLMError(f"timeout: {type(exc).__name__}") from exc
                except httpx.HTTPError as exc:
                    raise LLMError(
                        f"cannot reach the model server at {self.base_url}: "
                        f"{type(exc).__name__}"
                    ) from exc
                if response.status_code == 400 and position < len(self._formats) - 1:
                    # This server does not take that constraint. Step down and
                    # remember, so the next call does not repeat the failure.
                    position += 1
                    self.grammar = self._formats[position]
                    continue
                break
        assert response is not None
        status = response.status_code
        if status in (401, 403):
            raise LLMFatal(f"the model server rejected the key: {response.text[:200]}")
        if status == 404:
            raise LLMFatal(
                f"the server has no model {model!r} (HTTP 404): {response.text[:160]}"
            )
        if status in (429, 503):
            self.limiter.pushed_back()
            raise LLMError(f"server busy ({status}); concurrency lowered to {self.limiter.limit}")
        if status != 200:
            raise LLMError(f"model server {status}: {response.text[:200]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("the model server returned a reply that is not JSON") from exc
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("the model server returned no choices")
        self.limiter.ok()
        choice = choices[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        if not isinstance(text, str):
            text = ""
        text = strip_thinking(text)
        usage = data.get("usage") or {}
        tokens_in = usage.get("prompt_tokens") or 0
        tokens_out = usage.get("completion_tokens") or 0
        cost = None
        if model in self.prices:
            per_in, per_out = self.prices[model]
            cost = (tokens_in * per_in + tokens_out * per_out) / 1_000_000
        return LLMResult(
            text=text,
            model=data.get("model") or model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            latency_ms=int((time.monotonic() - started) * 1000),
            refused=False,
            cost=cost if cost is not None else 0.0,
        )

    async def list_models(self) -> list[dict]:
        response = await self._http.get(f"{self.base_url}/models", headers=self._headers)
        if response.status_code != 200:
            raise LLMError(f"model server {response.status_code}: {response.text[:200]}")
        return [{"id": m.get("id", "")} for m in response.json().get("data", [])]
