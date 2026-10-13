"""An offline LLM for tests and demos: scripted or rule-generated replies per role."""

import json
from collections.abc import Callable
from typing import Union

from pydantic import BaseModel

from tinyworld.llm.types import LLMRequest, LLMResult

Reply = Union[str, dict, BaseModel]
Handler = Union[Reply, list, Callable[[LLMRequest], Reply]]


def _text(reply: Reply) -> str:
    if isinstance(reply, BaseModel):
        return reply.model_dump_json()
    if isinstance(reply, dict):
        return json.dumps(reply)
    return reply


class FakeLLM:
    """Handlers are looked up by role; the longest matching prefix wins.

    A handler is a fixed reply, a list of replies consumed in order (the last
    one repeats), or a function of the request.
    """

    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self.calls: list[LLMRequest] = []
        self._positions: dict[str, int] = {}

    def on(self, role: str, handler: Handler) -> "FakeLLM":
        self.handlers[role] = handler
        self._positions.pop(role, None)
        return self

    def calls_for(self, role: str) -> list[LLMRequest]:
        return [call for call in self.calls if call.role.startswith(role)]

    def _handler(self, role: str) -> tuple[str, Handler]:
        best = ""
        for prefix in self.handlers:
            if prefix != "*" and role.startswith(prefix) and len(prefix) > len(best):
                best = prefix
        if best:
            return best, self.handlers[best]
        if "*" in self.handlers:
            return "*", self.handlers["*"]
        raise KeyError(f"FakeLLM has no handler for role {role!r}")

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        self.calls.append(request)
        key, handler = self._handler(request.role)
        if isinstance(handler, list):
            position = self._positions.get(key, 0)
            self._positions[key] = position + 1
            reply = handler[min(position, len(handler) - 1)]
        elif callable(handler):
            reply = handler(request)
        else:
            reply = handler
        text = _text(reply)
        prompt = request.system + request.stable_context + request.user
        return LLMResult(
            text=text,
            model=model,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
        )
