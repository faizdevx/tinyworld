"""Google Gemini client over the REST API (``generativelanguage.googleapis.com``).

Same contract as the Anthropic client: a request in, text and usage out, and
:class:`LLMError` for anything the caller should treat as a failed attempt.
Replies are validated by ``StructuredLLM`` regardless of what the model sends.
"""

import asyncio
import json
import os
import time

import httpx

from tinyworld.llm.client import provider_schema
from tinyworld.llm.types import LLMError, LLMRequest, LLMResult

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Finish reasons that mean the model declined, not that it ran out of room.
_REFUSALS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}
_RETRYABLE = {429, 500, 502, 503, 504}

# Thinking models spend output tokens on reasoning before they answer.
THINKING_HEADROOM = 2048


def api_key_from_env() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
        retries: int = 2,
        backoff: float = 1.5,
        sleep=asyncio.sleep,
        base_url: str = BASE_URL,
    ) -> None:
        key = api_key or api_key_from_env()
        if not key:
            raise LLMError("no Gemini API key: set GEMINI_API_KEY")
        self._key = key
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self.retries = retries
        self.backoff = backoff
        self._sleep = sleep
        self.base_url = base_url.rstrip("/")

    # -- requests ---------------------------------------------------------

    def _body(self, request: LLMRequest, *, with_schema: bool) -> dict:
        schema_text = json.dumps(request.schema, separators=(",", ":"))
        system = request.system
        if request.stable_context:
            system += "\n\n" + request.stable_context
        # The schema is also in the prompt: a model that ignores or rejects the
        # structured-output field still has to know the shape it is asked for.
        system += f"\n\nThe JSON object must match this JSON Schema:\n{schema_text}"
        config: dict = {
            "responseMimeType": "application/json",
            "maxOutputTokens": request.max_tokens + THINKING_HEADROOM,
        }
        if with_schema:
            config["responseJsonSchema"] = provider_schema(request.schema)
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": config,
        }

    async def _post(self, model: str, body: dict) -> httpx.Response:
        try:
            return await self._http.post(
                f"{self.base_url}/models/{model}:generateContent",
                headers={"x-goog-api-key": self._key, "Content-Type": "application/json"},
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise LLMError(f"timeout after {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"connection error: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            error = response.json().get("error", {})
            return f"{error.get('status', response.status_code)}: {error.get('message', response.text[:200])}"
        except ValueError:
            return f"{response.status_code}: {response.text[:200]}"

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        started = time.monotonic()
        with_schema = True
        response: httpx.Response | None = None
        for attempt in range(self.retries + 1):
            response = await self._post(model, self._body(request, with_schema=with_schema))
            if response.status_code == 400 and with_schema:
                # The schema used something the endpoint rejects. Ask again with
                # only the schema in the prompt; the reply is validated anyway.
                with_schema = False
                response = await self._post(model, self._body(request, with_schema=False))
            if response.status_code in _RETRYABLE and attempt < self.retries:
                await self._sleep(self.backoff * (2**attempt))
                continue
            break
        assert response is not None
        if response.status_code != 200:
            raise LLMError(f"gemini {self._message(response)}")

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("gemini returned a reply that is not JSON") from exc

        usage = data.get("usageMetadata", {})
        # Reasoning tokens are billed as output.
        output_tokens = (usage.get("candidatesTokenCount") or 0) + (
            usage.get("thoughtsTokenCount") or 0
        )
        latency = int((time.monotonic() - started) * 1000)
        blocked = (data.get("promptFeedback") or {}).get("blockReason")
        candidates = data.get("candidates") or []
        if blocked or not candidates:
            return LLMResult(
                text="", model=data.get("modelVersion", model),
                input_tokens=usage.get("promptTokenCount") or 0,
                output_tokens=output_tokens, latency_ms=latency, refused=True,
            )
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(
            part.get("text", "") for part in parts if not part.get("thought") and "text" in part
        )
        return LLMResult(
            text=text,
            model=data.get("modelVersion", model),
            input_tokens=usage.get("promptTokenCount") or 0,
            output_tokens=output_tokens,
            cache_read_tokens=usage.get("cachedContentTokenCount") or 0,
            latency_ms=latency,
            refused=candidate.get("finishReason") in _REFUSALS and not text,
        )

    # -- discovery --------------------------------------------------------

    async def list_models(self) -> list[dict]:
        """Models this key can call with ``generateContent``."""
        response = await self._http.get(
            f"{self.base_url}/models",
            headers={"x-goog-api-key": self._key},
            params={"pageSize": 200},
        )
        if response.status_code != 200:
            raise LLMError(f"gemini {self._message(response)}")
        return [
            {
                "id": model["name"].removeprefix("models/"),
                "display_name": model.get("displayName", ""),
                "input_limit": model.get("inputTokenLimit"),
                "output_limit": model.get("outputTokenLimit"),
            }
            for model in response.json().get("models", [])
            if "generateContent" in model.get("supportedGenerationMethods", [])
        ]
