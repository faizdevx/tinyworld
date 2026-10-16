"""Record a build, and replay it with no model and no web.

A studio run depends on three things outside the code: the model's replies, what
the web returned, and what the user answered. All three are recorded. A replay
serves them back, so the same draft comes out with no model call, no network and
nobody to ask.

Model calls are matched by who made them (agent and task), the step and the
role, not by their order. Searches and pages are matched by query and address.
That makes a replay safe even though agents ran at the same time.
"""

import json
from collections import defaultdict

from tinyworld.core.store import Store
from tinyworld.genesis.research import SearchHit, SearchProvider
from tinyworld.llm.trace import base_key
from tinyworld.llm.types import LLMError, LLMRequest, LLMResult


def ensure_tables(store: Store) -> None:
    store.execute(
        "CREATE TABLE IF NOT EXISTS studio_tool_calls ("
        "world_id TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, "
        "ordinal INTEGER NOT NULL, result_json TEXT NOT NULL, "
        "PRIMARY KEY (world_id, kind, key, ordinal))"
    )


def _hit(hit: SearchHit) -> dict:
    return {"url": hit.url, "title": hit.title, "snippet": hit.snippet, "provider": hit.provider}


class RecordingSearch:
    """Wraps a search provider and writes down every answer it gives."""

    def __init__(self, inner: SearchProvider, store: Store, world_id: str) -> None:
        self.inner = inner
        self.store = store
        self.world_id = world_id
        self._count: dict[tuple[str, str], int] = defaultdict(int)
        ensure_tables(store)

    def _write(self, kind: str, key: str, result) -> None:
        ordinal = self._count[(kind, key)]
        self._count[(kind, key)] += 1
        self.store.execute(
            "INSERT OR REPLACE INTO studio_tool_calls VALUES (?,?,?,?,?)",
            (self.world_id, kind, key, ordinal, json.dumps(result)),
        )

    async def search(self, query: str, limit: int = 3) -> list[SearchHit]:
        hits = await self.inner.search(query, limit)
        self._write("search", query, [_hit(h) for h in hits])
        return hits

    async def fetch(self, hit: SearchHit) -> str:
        text = await self.inner.fetch(hit)
        self._write("fetch", hit.url, text)
        return text


class ReplaySearch:
    """Serves what a recorded build saw. A question it never saw is an error."""

    def __init__(self, store: Store, source_world: str) -> None:
        self.store = store
        self.source = source_world
        self._count: dict[tuple[str, str], int] = defaultdict(int)
        ensure_tables(store)

    def _read(self, kind: str, key: str):
        ordinal = self._count[(kind, key)]
        self._count[(kind, key)] += 1
        rows = self.store.query(
            "SELECT result_json FROM studio_tool_calls "
            "WHERE world_id=? AND kind=? AND key=? AND ordinal=?",
            (self.source, kind, key, ordinal),
        )
        if not rows:
            # The same thing asked more often than before: repeat the last answer.
            rows = self.store.query(
                "SELECT result_json FROM studio_tool_calls "
                "WHERE world_id=? AND kind=? AND key=? ORDER BY ordinal DESC LIMIT 1",
                (self.source, kind, key),
            )
        if not rows:
            raise LookupError(f"the recorded build never made this {kind}: {key!r}")
        return json.loads(rows[0]["result_json"])

    async def search(self, query: str, limit: int = 3) -> list[SearchHit]:
        return [SearchHit(**h) for h in self._read("search", query)]

    async def fetch(self, hit: SearchHit) -> str:
        return self._read("fetch", hit.url)


class StudioReplayLLM:
    """Serves the model replies recorded for a studio, with no provider calls."""

    def __init__(self, store: Store, source_world: str) -> None:
        self.store = store
        self.source = source_world
        self._ordinals: dict[str, int] = defaultdict(int)

    async def complete(
        self, request: LLMRequest, model: str, effort: str | None
    ) -> LLMResult:
        key = base_key(request.role, request.context)
        ordinal = self._ordinals[key]
        self._ordinals[key] += 1
        rows = self.store.query(
            "SELECT * FROM llm_calls WHERE branch_id=? AND cache_key=?",
            (self.source, f"{key}|{ordinal}"),
        )
        if not rows:
            raise LLMError(f"no recorded call for {key}|{ordinal}")
        row = rows[0]
        reply = json.loads(row["response_json"])
        return LLMResult(
            text=reply["text"], model=row["model"], input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"], refused=reply.get("refused", False),
            cost=row["cost"],
        )
