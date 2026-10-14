"""OpenRouter client (OpenAI-compatible chat completions, any hosted model).

One key reaches many models, so the model for each tier is just a string:
set OPENROUTER_MODEL_STRONG, OPENROUTER_MODEL_STANDARD and
OPENROUTER_MODEL_CHEAP, or change them in the JSON config file.
"""

import asyncio
import json
import os
import re
import time
from collections import deque

import httpx

from tinyworld.llm.client import provider_schema
from tinyworld.llm.types import LLMError, LLMFatal, LLMRequest, LLMResult

BASE_URL = "https://openrouter.ai/api/v1"
_RETRYABLE = {408, 429, 500, 502, 503, 504}
MAX_WAIT = 60.0
REASONING_HEADROOM = 256
_AFFORD = re.compile(r"can only afford (\d+)")
# Below this many affordable tokens a reply is more likely cut off than useful.
MIN_AFFORDABLE = 400


def api_key_from_env() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY")


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 180.0,
        retries: int = 3,
        backoff: float = 2.0,
        sleep=asyncio.sleep,
        base_url: str = BASE_URL,
        max_concurrent: int | None = None,
        requests_per_minute: int | None = None,
        clock=time.monotonic,
        site_url: str = "https://github.com/faizdevx/tinyworld",
        site_name: str = "TinyWorld",
        reasoning: bool | None = None,
    ) -> None:
        key = api_key or api_key_from_env()
        if not key:
            raise LLMError("no OpenRouter API key: set OPENROUTER_API_KEY")
        self._key = key
        # Hidden reasoning multiplies output tokens and latency many times over,
        # and every call here is a bounded structured task. Off unless asked
        # for with OPENROUTER_REASONING=on. Models without it ignore the field.
        self.reasoning = (
            reasoning
            if reasoning is not None
            else os.environ.get("OPENROUTER_REASONING", "off").lower() in ("on", "1", "true")
        )
        self._reasoning_only: set[str] = set()
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Optional attribution headers OpenRouter uses for its rankings.
            "HTTP-Referer": site_url,
            "X-Title": site_name,
        }
        limit = max_concurrent or int(os.environ.get("OPENROUTER_CONCURRENCY", "6"))
        self._slots = asyncio.Semaphore(max(1, limit))
        self.rpm = (
            requests_per_minute
            if requests_per_minute is not None
            else int(os.environ.get("OPENROUTER_RPM", "0"))
        )
        self._sent: deque[float] = deque()
        self._pace_lock = asyncio.Lock()
        self._clock = clock

    async def _pace(self) -> None:
        if self.rpm <= 0:
            return
        async with self._pace_lock:
            while True:
                now = self._clock()
                while self._sent and now - self._sent[0] >= 60.0:
                    self._sent.popleft()
                if len(self._sent) < self.rpm:
                    self._sent.append(now)
                    return
                await self._sleep(60.0 - (now - self._sent[0]) + 0.05)

    # -- requests ---------------------------------------------------------

    def _body(self, request: LLMRequest, model: str, *, json_mode: bool, schema: bool) -> dict:
        system = request.system
        if request.stable_context:
            system += "\n\n" + request.stable_context
        # The schema goes in the prompt as well: not every hosted model
        # honours a response format, and none can be trusted to.
        system += "\n\nThe JSON object must match this JSON Schema:\n" + json.dumps(
            request.schema, separators=(",", ":")
        )
        # Some models cannot run without reasoning. Learned from the first
        # rejection, then remembered for the rest of the run.
        forced = model in self._reasoning_only
        body: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": request.max_tokens
            + (REASONING_HEADROOM if (self.reasoning or forced) else 0),
            "usage": {"include": True},
        }
        if forced and not self.reasoning:
            body["reasoning"] = {"effort": "low"}
        elif not self.reasoning:
            body["reasoning"] = {"enabled": False}
        if schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name or "response",
                    "strict": False,
                    "schema": provider_schema(request.schema),
                },
            }
        elif json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def _post(self, body: dict) -> httpx.Response:
        try:
            async with self._slots:
                await self._pace()
                return await self._http.post(
                    f"{self.base_url}/chat/completions", headers=self._headers, json=body
                )
        except httpx.TimeoutException as exc:
            raise LLMError(f"timeout: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"connection error: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            error = response.json().get("error", {})
            detail = error.get("message") or response.text[:200]
            metadata = error.get("metadata") or {}
            raw = metadata.get("raw")
            if raw:
                detail += f" ({str(raw)[:160]})"
            return f"{response.status_code}: {detail}"
        except (ValueError, AttributeError):
            return f"{response.status_code}: {response.text[:200]}"

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            return float(response.headers.get("retry-after", "0"))
        except ValueError:
            return 0.0

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        started = time.monotonic()
        # Most specific format first; step down when the model rejects it.
        formats = [(True, True), (True, False), (False, False)]
        position = 0
        response: httpx.Response | None = None
        waits = 0
        cap: int | None = None  # set when the balance cannot cover the request
        while True:
            json_mode, schema = formats[position]
            body = self._body(request, model, json_mode=json_mode, schema=schema)
            if cap is not None:
                body["max_tokens"] = cap
            response = await self._post(body)
            status = response.status_code
            if status == 402 and cap is None:
                # OpenRouter reserves the full max_tokens against the balance.
                # Ask again for what can be afforded rather than failing.
                found = _AFFORD.search(response.text)
                if found and int(found.group(1)) >= MIN_AFFORDABLE:
                    cap = int(found.group(1)) - 16
                    continue
            if (
                status == 400
                and model not in self._reasoning_only
                and "reasoning is mandatory" in response.text.lower()
            ):
                self._reasoning_only.add(model)
                continue
            if status == 400 and position < len(formats) - 1:
                position += 1
                continue
            if status in _RETRYABLE and waits < self.retries:
                wait = max(self.backoff * (2**waits), self._retry_after(response))
                if wait > MAX_WAIT * 4:
                    break  # a delay that long is a quota, not a hiccup
                waits += 1
                await self._sleep(min(wait, MAX_WAIT))
                continue
            break
        assert response is not None
        if response.status_code == 401:
            raise LLMFatal(f"openrouter rejected the key: {self._message(response)}")
        if response.status_code == 402:
            raise LLMFatal(
                f"openrouter out of credits: {self._message(response)}. "
                "Add credit, or use a :free model or a cheaper one."
            )
        if response.status_code != 200:
            raise LLMError(f"openrouter {self._message(response)}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("openrouter returned a reply that is not JSON") from exc
        if isinstance(data.get("error"), dict):
            # Some upstream failures arrive as a 200 with an error body.
            raise LLMError(f"openrouter {data['error'].get('message', 'error')}")

        choices = data.get("choices") or []
        if not choices:
            raise LLMError("openrouter returned no choices")
        choice = choices[0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        cost = usage.get("cost")
        return LLMResult(
            text=text if isinstance(text, str) else "",
            model=data.get("model") or model,
            input_tokens=usage.get("prompt_tokens") or 0,
            output_tokens=usage.get("completion_tokens") or 0,
            cache_read_tokens=details.get("cached_tokens") or 0,
            latency_ms=int((time.monotonic() - started) * 1000),
            refused=choice.get("finish_reason") == "content_filter" and not text,
            cost=float(cost) if isinstance(cost, (int, float)) else None,
        )

    # -- discovery --------------------------------------------------------

    async def key_info(self) -> dict:
        """Usage and limit of this key (``GET /key``)."""
        response = await self._http.get(f"{self.base_url}/key", headers=self._headers)
        if response.status_code != 200:
            raise LLMError(f"openrouter {self._message(response)}")
        return response.json().get("data", {})

    async def list_models(self) -> list[dict]:
        response = await self._http.get(f"{self.base_url}/models", headers=self._headers)
        if response.status_code != 200:
            raise LLMError(f"openrouter {self._message(response)}")
        found = []
        for model in response.json().get("data", []):
            pricing = model.get("pricing") or {}
            found.append(
                {
                    "id": model["id"],
                    "display_name": model.get("name", ""),
                    "input_limit": model.get("context_length"),
                    "output_limit": (model.get("top_provider") or {}).get("max_completion_tokens"),
                    "prompt_price": pricing.get("prompt"),
                    "completion_price": pricing.get("completion"),
                }
            )
        return found
