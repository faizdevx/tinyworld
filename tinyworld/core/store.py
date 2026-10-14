"""SQLite persistence for worlds, branches, events and snapshots.

A branch reads its own rows plus each ancestor's rows up to the point where
the next branch in the lineage forked. Forking therefore copies nothing.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime

from pydantic import TypeAdapter

from tinyworld.core.effects import Effect
from tinyworld.core.events import Event
from tinyworld.core.registry import REGISTRY, AttrRegistry
from tinyworld.core.reducers import apply_event_in_place
from tinyworld.core.state import WorldState

_EFFECTS = TypeAdapter(list[Effect])

SCHEMA = """
CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    premise TEXT NOT NULL,
    start_time TEXT NOT NULL,
    created_at TEXT NOT NULL,
    bible_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS branches (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id),
    parent_id TEXT REFERENCES branches(id),
    fork_seq INTEGER,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    start_time TEXT
);
CREATE TABLE IF NOT EXISTS events (
    branch_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    sim_time TEXT NOT NULL,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    location TEXT,
    payload_json TEXT NOT NULL,
    causes_json TEXT NOT NULL,
    visibility TEXT NOT NULL,
    trace_id TEXT,
    PRIMARY KEY (branch_id, seq)
);
CREATE INDEX IF NOT EXISTS events_actor ON events(branch_id, actor, seq);
CREATE TABLE IF NOT EXISTS snapshots (
    branch_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    PRIMARY KEY (branch_id, seq)
);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    created_seq INTEGER NOT NULL,
    sim_time TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    importance REAL NOT NULL,
    embedding BLOB,
    source_events_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    participants_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS memories_agent ON memories(branch_id, agent, created_seq);
CREATE TABLE IF NOT EXISTS memory_supersedes (
    branch_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    superseded_by TEXT NOT NULL,
    at_seq INTEGER NOT NULL,
    PRIMARY KEY (branch_id, memory_id)
);
CREATE TABLE IF NOT EXISTS beliefs (
    branch_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT,
    origin TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    as_of_seq INTEGER NOT NULL,
    as_of TEXT NOT NULL,
    row_id INTEGER PRIMARY KEY AUTOINCREMENT
);
CREATE INDEX IF NOT EXISTS beliefs_agent ON beliefs(branch_id, agent, as_of_seq);
CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    tick_seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    agent TEXT,
    ordinal INTEGER NOT NULL,
    model TEXT NOT NULL,
    tier TEXT NOT NULL,
    request_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    cache_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS llm_calls_key ON llm_calls(branch_id, cache_key);
CREATE TABLE IF NOT EXISTS bible (
    world_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    section TEXT NOT NULL,
    content_json TEXT NOT NULL,
    PRIMARY KEY (world_id, version, section)
);
CREATE TABLE IF NOT EXISTS sources (
    world_id TEXT NOT NULL,
    id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    text TEXT NOT NULL,
    notes_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (world_id, id)
);
CREATE TABLE IF NOT EXISTS scheduled (
    id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL,
    created_seq INTEGER NOT NULL,
    due_time TEXT NOT NULL,
    draft_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    branch_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    seq_before INTEGER NOT NULL,
    op TEXT NOT NULL,
    args_json TEXT NOT NULL,
    PRIMARY KEY (branch_id, ordinal)
);
CREATE TABLE IF NOT EXISTS meta (
    world_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (world_id, key)
);
CREATE TABLE IF NOT EXISTS scheduled_done (
    branch_id TEXT NOT NULL,
    scheduled_id TEXT NOT NULL,
    at_seq INTEGER NOT NULL,
    PRIMARY KEY (branch_id, scheduled_id)
);
"""


class StoreError(RuntimeError):
    pass


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # -- low level ------------------------------------------------------

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._db.execute(sql, params)
            self._db.commit()
            return cursor

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        with self._lock:
            self._db.executemany(sql, rows)
            self._db.commit()

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # -- worlds and branches --------------------------------------------

    def create_world(
        self,
        premise: str,
        start_time: datetime,
        *,
        world_id: str | None = None,
    ) -> str:
        world_id = world_id or new_id()
        self.execute(
            "INSERT INTO worlds (id, premise, start_time, created_at) VALUES (?,?,?,?)",
            (world_id, premise, start_time.isoformat(), datetime.now().isoformat()),
        )
        return world_id

    def world(self, world_id: str) -> sqlite3.Row:
        rows = self.query("SELECT * FROM worlds WHERE id=?", (world_id,))
        if not rows:
            raise StoreError(f"unknown world: {world_id}")
        return rows[0]

    def worlds(self) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM worlds ORDER BY created_at")

    def create_branch(
        self,
        world_id: str,
        name: str = "main",
        *,
        parent_id: str | None = None,
        fork_seq: int | None = None,
        branch_id: str | None = None,
        start_time: datetime | None = None,
    ) -> str:
        """Create a branch. A root branch may fix its own starting time."""
        self.world(world_id)
        branch_id = branch_id or new_id()
        self.execute(
            "INSERT INTO branches (id, world_id, parent_id, fork_seq, name, created_at,"
            " start_time) VALUES (?,?,?,?,?,?,?)",
            (
                branch_id, world_id, parent_id, fork_seq, name,
                datetime.now().isoformat(),
                start_time.isoformat() if start_time else None,
            ),
        )
        return branch_id

    def branch(self, branch_id: str) -> sqlite3.Row:
        rows = self.query("SELECT * FROM branches WHERE id=?", (branch_id,))
        if not rows:
            raise StoreError(f"unknown branch: {branch_id}")
        return rows[0]

    def branches(self, world_id: str) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM branches WHERE world_id=? ORDER BY created_at, id",
            (world_id,),
        )

    def lineage(self, branch_id: str) -> list[tuple[str, int | None]]:
        """Root-first list of (branch, highest visible seq). None means no limit."""
        chain: list[tuple[str, int | None]] = []
        limit: int | None = None
        current: str | None = branch_id
        while current is not None:
            row = self.branch(current)
            chain.append((current, limit))
            limit = row["fork_seq"] if limit is None else min(limit, row["fork_seq"] or 0)
            current = row["parent_id"]
        return chain[::-1]

    def lineage_clause(
        self, branch_id: str, seq_column: str, *, before: bool = False
    ) -> tuple[str, list]:
        """SQL predicate selecting rows visible from ``branch_id``.

        ``before`` selects ancestor rows strictly below the fork point. Use it
        for rows stamped with the seq a tick started at, since such a row
        belongs to events that come after that seq.
        """
        parts: list[str] = []
        params: list = []
        compare = "<" if before else "<="
        for ancestor, limit in self.lineage(branch_id):
            if limit is None:
                parts.append("(branch_id=?)")
                params.append(ancestor)
            else:
                parts.append(f"(branch_id=? AND {seq_column}{compare}?)")
                params.extend([ancestor, limit])
        return "(" + " OR ".join(parts) + ")", params

    def fork(self, branch_id: str, at_seq: int, name: str) -> str:
        if not 0 <= at_seq <= self.head_seq(branch_id):
            raise StoreError(f"cannot fork {branch_id} at seq {at_seq}")
        world_id = self.branch(branch_id)["world_id"]
        return self.create_branch(
            world_id, name, parent_id=branch_id, fork_seq=at_seq
        )

    # -- events ---------------------------------------------------------

    def head_seq(self, branch_id: str) -> int:
        clause, params = self.lineage_clause(branch_id, "seq")
        row = self.query(f"SELECT MAX(seq) AS head FROM events WHERE {clause}", params)[0]
        return row["head"] or 0

    def append(self, events: list[Event]) -> None:
        rows = [
            (
                event.branch_id,
                event.seq,
                event.sim_time.isoformat(),
                event.kind,
                event.actor,
                event.location,
                json.dumps(
                    {
                        "effects": [e.model_dump(mode="json") for e in event.effects],
                        "narration": event.narration,
                        "loud": event.loud,
                    }
                ),
                json.dumps(event.causes),
                event.visibility,
                event.trace_id,
            )
            for event in events
        ]
        try:
            self.executemany(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)", rows
            )
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"event sequence conflict: {exc}") from exc

    @staticmethod
    def _event(row: sqlite3.Row) -> Event:
        payload = json.loads(row["payload_json"])
        return Event(
            branch_id=row["branch_id"],
            seq=row["seq"],
            sim_time=datetime.fromisoformat(row["sim_time"]),
            kind=row["kind"],
            actor=row["actor"],
            location=row["location"],
            effects=_EFFECTS.validate_python(payload["effects"]),
            narration=payload["narration"],
            loud=payload.get("loud", False),
            causes=json.loads(row["causes_json"]),
            visibility=row["visibility"],
            trace_id=row["trace_id"],
        )

    def events(
        self,
        branch_id: str,
        *,
        after: int = 0,
        upto: int | None = None,
        actor: str | None = None,
        kind: str | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> list[Event]:
        clause, params = self.lineage_clause(branch_id, "seq")
        sql = f"SELECT * FROM events WHERE {clause} AND seq>?"
        params.append(after)
        if upto is not None:
            sql += " AND seq<=?"
            params.append(upto)
        if actor is not None:
            sql += " AND actor=?"
            params.append(actor)
        if kind is not None:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY seq DESC" if newest_first else " ORDER BY seq"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [self._event(row) for row in self.query(sql, params)]

    def event(self, branch_id: str, seq: int) -> Event | None:
        found = self.events(branch_id, after=seq - 1, upto=seq)
        return found[0] if found else None

    def last_seq_by_actor(self, branch_id: str, actor: str) -> int:
        clause, params = self.lineage_clause(branch_id, "seq")
        row = self.query(
            f"SELECT MAX(seq) AS head FROM events WHERE {clause} AND actor=?",
            params + [actor],
        )[0]
        return row["head"] or 0

    def seq_at_time(self, branch_id: str, when: datetime) -> int:
        """The last event at or before ``when``; 0 when there is none."""
        clause, params = self.lineage_clause(branch_id, "seq")
        row = self.query(
            f"SELECT MAX(seq) AS head FROM events WHERE {clause} AND sim_time<=?",
            params + [when.isoformat()],
        )[0]
        return row["head"] or 0

    def meta_set(self, world_id: str, key: str, value: str) -> None:
        self.execute("INSERT OR REPLACE INTO meta VALUES (?,?,?)", (world_id, key, value))

    def meta_get(self, world_id: str, key: str) -> str | None:
        rows = self.query("SELECT value FROM meta WHERE world_id=? AND key=?", (world_id, key))
        return rows[0]["value"] if rows else None

    # -- journal --------------------------------------------------------

    def journal_add(self, branch_id: str, seq_before: int, op: str, args: dict) -> None:
        """Record something that drove this branch, so the run can be replayed."""
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 AS next FROM journal WHERE branch_id=?",
                (branch_id,),
            ).fetchone()
            self._db.execute(
                "INSERT INTO journal VALUES (?,?,?,?,?)",
                (branch_id, row["next"], seq_before, op, json.dumps(args)),
            )
            self._db.commit()

    def journal(self, branch_id: str) -> list[sqlite3.Row]:
        """This branch's own driving operations, in order."""
        return self.query(
            "SELECT * FROM journal WHERE branch_id=? ORDER BY ordinal", (branch_id,)
        )

    # -- snapshots and state --------------------------------------------

    def save_snapshot(self, branch_id: str, state: WorldState) -> None:
        self.execute(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
            (branch_id, state.seq, state.model_dump_json()),
        )

    def nearest_snapshot(self, branch_id: str, upto: int) -> WorldState | None:
        clause, params = self.lineage_clause(branch_id, "seq")
        rows = self.query(
            f"SELECT state_json FROM snapshots WHERE {clause} AND seq<=?"
            " ORDER BY seq DESC LIMIT 1",
            params + [upto],
        )
        return WorldState.model_validate_json(rows[0]["state_json"]) if rows else None

    def initial_state(self, branch_id: str) -> WorldState:
        root = self.branch(self.lineage(branch_id)[0][0])
        start = root["start_time"] or self.world(root["world_id"])["start_time"]
        return WorldState(sim_time=datetime.fromisoformat(start))

    def state_at(
        self,
        branch_id: str,
        seq: int | None = None,
        *,
        use_snapshots: bool = True,
        registry: AttrRegistry = REGISTRY,
    ) -> WorldState:
        """Rebuild state at ``seq`` (default: head) from a snapshot plus the tail."""
        head = self.head_seq(branch_id)
        target = head if seq is None else seq
        if not 0 <= target <= head:
            raise StoreError(f"branch {branch_id} has no seq {target}")
        state = self.nearest_snapshot(branch_id, target) if use_snapshots else None
        if state is None:
            state = self.initial_state(branch_id)
        for event in self.events(branch_id, after=state.seq, upto=target):
            apply_event_in_place(state, event, registry)
        return state
