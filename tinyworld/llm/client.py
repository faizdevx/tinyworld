"""Anthropic client. Imported lazily so the simulation runs without the SDK."""

import copy
import time

from tinyworld.llm.types import LLMError, LLMRequest, LLMResult

# JSON Schema keywords the structured-output endpoint may not accept. Pydantic
# validates these after the call, so dropping them here loses nothing.
_UNSUPPORTED = (
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "pattern", "format", "default", "title",
    "discriminator", "minItems", "maxItems", "multipleOf",
)


def provider_schema(schema: dict) -> dict:
    """A copy of ``schema`` restricted to widely supported keywords."""

    def clean(node):
        if isinstance(node, dict):
            cleaned = {
                key: clean(value)
                for key, value in node.items()
                if key not in _UNSUPPORTED
            }
            if cleaned.get("type") == "object" and "properties" in cleaned:
                cleaned["additionalProperties"] = False
                cleaned["required"] = list(cleaned["properties"])
            return cleaned
        if isinstance(node, list):
            return [clean(item) for item in node]
        return node

    return clean(copy.deepcopy(schema))


class AnthropicClient:
    """Calls the Messages API with schema-constrained output and prompt caching."""

    def __init__(self, *, constrained: bool = True, timeout: float = 120.0) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(timeout=timeout)
        self.constrained = constrained

    def _system(self, request: LLMRequest) -> list[dict]:
        # The cache breakpoint sits after the stable context, so the rules and
        # the world digest are reused across every agent and tick.
        blocks = [{"type": "text", "text": request.system}]
        if request.stable_context:
            blocks.append({"type": "text", "text": request.stable_context})
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
        return blocks

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        anthropic = self._anthropic
        output_config: dict = {}
        if effort:
            output_config["effort"] = effort
        if self.constrained:
            output_config["format"] = {
                "type": "json_schema",
                "schema": provider_schema(request.schema),
            }
        params = dict(
            model=model,
            max_tokens=request.max_tokens,
            system=self._system(request),
            messages=[{"role": "user", "content": request.user}],
        )
        if output_config:
            params["output_config"] = output_config

        started = time.monotonic()
        try:
            try:
                response = await self._client.messages.create(**params)
            except anthropic.BadRequestError:
                if "format" not in output_config:
                    raise
                # The schema used a construct the endpoint rejects. Ask again
                # without the constraint; the caller still validates the reply.
                output_config.pop("format")
                if output_config:
                    params["output_config"] = output_config
                else:
                    params.pop("output_config")
                response = await self._client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise LLMError(f"rate limited: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"api error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"connection error: {exc}") from exc

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        usage = response.usage
        return LLMResult(
            text=text,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            latency_ms=int((time.monotonic() - started) * 1000),
            refused=response.stop_reason == "refusal",
        )
