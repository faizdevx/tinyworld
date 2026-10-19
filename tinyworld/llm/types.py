"""Request and result types shared by every LLM client."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CallContext:
    """Where a call belongs. Together with the role it identifies the call on replay."""

    branch_id: str
    tick_seq: int = 0
    agent: str | None = None


@dataclass
class LLMRequest:
    role: str
    # Stable text goes first so provider prompt caching can reuse it.
    system: str
    user: str
    schema: dict
    schema_name: str = "response"
    stable_context: str = ""
    max_tokens: int = 4000
    # Sampling temperature; None leaves the provider's default.
    temperature: float | None = None
    context: CallContext = field(default_factory=lambda: CallContext("none"))


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    refused: bool = False
    # Cost in dollars when the provider reports it; otherwise computed from prices.
    cost: float | None = None


class LLMClient(Protocol):
    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult: ...


class LLMError(RuntimeError):
    """A provider call failed in a way the caller should treat as a bad attempt."""


class LLMFatal(LLMError):
    """A failure no retry or fallback can fix: a bad or expired key, no credit.

    Unlike other errors this is not swallowed into a safe default. Carrying on
    would produce a world in which everyone silently does nothing.
    """
