"""Recording of every LLM call, and replay from the recording."""

import json
from collections import defaultdict

from tinyworld.core.store import Store
from tinyworld.llm.router import LLMConfig, Route
from tinyworld.llm.types import CallContext, LLMError, LLMRequest, LLMResult


def base_key(role: str, context: CallContext) -> str:
    return f"{context.tick_seq}|{role}|{context.agent or '-'}"


class Tracer:
    """Writes one ``llm_calls`` row per attempt."""

    def __init__(self, store: Store, config: LLMConfig) -> None:
        self.store = store
        self.config = config
        self._ordinals: dict[tuple[str, str], int] = {}

    def _next_ordinal(self, branch_id: str, key: str) -> int:
        marker = (branch_id, key)
        if marker not in self._ordinals:
            # Continue after rows from an earlier process on the same branch.
            row = self.store.query(
                "SELECT COUNT(*) AS n FROM llm_calls WHERE branch_id=? AND cache_key LIKE ?",
                (branch_id, key + "|%"),
            )[0]
            self._ordinals[marker] = row["n"]
        ordinal = self._ordinals[marker]
        self._ordinals[marker] = ordinal + 1
        return ordinal

    def record(self, request: LLMRequest, route: Route, result: LLMResult) -> str:
        context = request.context
        key = base_key(request.role, context)
        ordinal = self._next_ordinal(context.branch_id, key)
        call_id = f"{context.branch_id}|{key}|{ordinal}"
        cost = self.config.cost(
            result.model,
            result.input_tokens,
            result.output_tokens,
            result.cache_read_tokens,
            result.cache_write_tokens,
        )
        self.store.execute(
            "INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                call_id,
                context.branch_id,
                context.tick_seq,
                request.role,
                context.agent,
                ordinal,
                result.model,
                route.tier,
                json.dumps(
                    {
                        "system": request.system,
                        "stable_context": request.stable_context,
                        "user": request.user,
                        "schema_name": request.schema_name,
                    }
                ),
                json.dumps(
                    {
                        "text": result.text,
                        "refused": result.refused,
                        "cache_read_tokens": result.cache_read_tokens,
                        "cache_write_tokens": result.cache_write_tokens,
                    }
                ),
                result.input_tokens,
                result.output_tokens,
                cost,
                result.latency_ms,
                f"{key}|{ordinal}",
            ),
        )
        return call_id


class ReplayLLM:
    """Serves the responses recorded on ``source_branch``, in the same order.

    Calls are matched by tick, role, agent and their ordinal within those, so
    replay does not depend on prompts being byte-identical.
    """

    def __init__(self, store: Store, source_branch: str) -> None:
        self.store = store
        self.source_branch = source_branch
        self._ordinals: dict[str, int] = defaultdict(int)

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        key = base_key(request.role, request.context)
        ordinal = self._ordinals[key]
        self._ordinals[key] += 1
        clause, params = self.store.lineage_clause(
            self.source_branch, "tick_seq", before=True
        )
        rows = self.store.query(
            f"SELECT * FROM llm_calls WHERE {clause} AND cache_key=?",
            params + [f"{key}|{ordinal}"],
        )
        if not rows:
            raise LLMError(f"no recorded call for {key}|{ordinal}")
        row = rows[0]
        response = json.loads(row["response_json"])
        # Usage is replayed too, so decisions that depend on cost repeat exactly.
        return LLMResult(
            text=response["text"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cache_read_tokens=response.get("cache_read_tokens", 0),
            cache_write_tokens=response.get("cache_write_tokens", 0),
            refused=response.get("refused", False),
        )
