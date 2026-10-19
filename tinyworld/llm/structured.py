"""The one entry point for LLM calls: schema in, validated model out, never raises."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from tinyworld.llm.router import LLMConfig
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import CallContext, LLMClient, LLMError, LLMFatal, LLMRequest

T = TypeVar("T", bound=BaseModel)

JSON_ONLY = (
    "Reply with a single JSON object that matches the schema. "
    "No prose before or after it."
)


@dataclass
class Structured(Generic[T]):
    value: T
    ok: bool
    trace_id: str | None
    attempts: int
    error: str = ""


def extract_json(text: str) -> str:
    """The outermost JSON object in ``text``, tolerating code fences and prose."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return text[start : end + 1]


_SCHEMAS: dict = {}


def _schema_of(schema) -> dict:
    """The JSON schema of a reply type, made once. Callers must not change it."""
    found = _SCHEMAS.get(schema)
    if found is None:
        found = _SCHEMAS[schema] = schema.model_json_schema()
    return found


class StructuredLLM:
    def __init__(
        self,
        client: LLMClient,
        config: LLMConfig,
        tracer: Tracer | None = None,
        *,
        max_repairs: int = 2,
    ) -> None:
        self.client = client
        self.config = config
        self.tracer = tracer
        self.max_repairs = max_repairs

    async def call(
        self,
        role: str,
        schema: type[T],
        *,
        system: str,
        user: str,
        context: CallContext,
        fallback: T | Callable[[str], T],
        stable_context: str = "",
        max_tokens: int = 4000,
        temperature: float | None = None,
        check: Callable[[T], str | None] | None = None,
    ) -> Structured[T]:
        """Call the model for ``role`` and validate the reply against ``schema``.

        ``check`` may reject a schema-valid reply by returning a reason. A bad
        reply is retried with the error attached, up to ``max_repairs`` times.
        After that ``fallback`` is returned with ``ok=False``.
        """
        route = self.config.route(role, context.agent)
        json_schema = _schema_of(schema)
        prompt = user
        error = ""
        trace_id: str | None = None
        attempts = 0

        for _ in range(self.max_repairs + 1):
            attempts += 1
            request = LLMRequest(
                role=role,
                system=f"{system}\n\n{JSON_ONLY}",
                stable_context=stable_context,
                user=prompt,
                schema=json_schema,
                schema_name=schema.__name__,
                max_tokens=max_tokens,
                temperature=temperature,
                context=context,
            )
            try:
                result = await self.client.complete(request, route.model, route.effort)
            except LLMFatal:
                raise
            except LLMError as exc:
                error = str(exc)
                continue
            except Exception as exc:  # a provider bug must not stop the simulation
                error = f"{type(exc).__name__}: {exc}"
                continue

            if self.tracer is not None:
                trace_id = self.tracer.record(request, route, result)

            if result.refused:
                error = "the model declined this request"
                break
            try:
                value = schema.model_validate(json.loads(extract_json(result.text)))
                reason = check(value) if check is not None else None
                if reason is None:
                    return Structured(value, True, trace_id, attempts)
                error = reason
            except (ValueError, ValidationError) as exc:
                error = str(exc)

            prompt = (
                f"{user}\n\nYour previous reply was rejected:\n{error[:1500]}\n"
                "Send a corrected JSON object."
            )

        value = fallback(error) if callable(fallback) else fallback
        return Structured(value, False, trace_id, attempts, error)
