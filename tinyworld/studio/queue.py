"""A durable queue of studio builds, shared by any number of workers.

A build is a job. The API (or a person at a terminal) enqueues it; a worker
process claims it, runs the team, and keeps a lease alive while it works. If the
worker dies, the lease runs out and another worker picks the job up: the studio
state is saved after every step, so the build carries on where it stopped
instead of starting over.

Fair sharing: a job's tenant is whoever asked for it. When several are waiting,
the next one comes from the tenant with the fewest builds running, oldest
first, so one person queueing twenty builds does not starve everyone else. A cap
on running builds keeps a small machine from running too many models at once.

The queue lives in the same database as the worlds (SQLite today). Every
statement is plain SQL with the ``?`` placeholder, and the claim is one atomic
conditional UPDATE, so moving it to Postgres is a change of driver and
``FOR UPDATE SKIP LOCKED``, not of design. That move is not made yet.
"""

import json
import time
from dataclasses import dataclass

from tinyworld.core.store import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_jobs (
    world_id TEXT PRIMARY KEY,
    tenant TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '',
    lease_until REAL NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    enqueued_at REAL NOT NULL,
    finished_at REAL,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS studio_jobs_status ON studio_jobs (status, enqueued_at);
"""
# status: queued | running | done | failed | cancelled

MAX_ATTEMPTS = 3


@dataclass
class Job:
    world_id: str
    tenant: str
    status: str
    payload: dict
    owner: str
    lease_until: float
    attempts: int
    enqueued_at: float
    error: str = ""


def _job(row) -> Job:
    return Job(
        world_id=row["world_id"], tenant=row["tenant"], status=row["status"],
        payload=json.loads(row["payload"]), owner=row["owner"],
        lease_until=row["lease_until"], attempts=row["attempts"],
        enqueued_at=row["enqueued_at"], error=row["error"],
    )


class JobQueue:
    def __init__(self, store: Store, *, now=time.time, max_running: int = 2) -> None:
        self.store = store
        self.now = now
        self.max_running = max_running
        for statement in SCHEMA.split(";"):
            if statement.strip():
                store.execute(statement)

    # -- producers ------------------------------------------------------

    def enqueue(self, world_id: str, goal: str, *, tenant: str = "default",
                auto: bool = True, budget: float | None = None) -> Job:
        """Queue a build. Asking again for a world already queued or running changes nothing."""
        existing = self.get(world_id)
        if existing is not None and existing.status in ("queued", "running"):
            return existing
        payload = json.dumps({"goal": goal, "auto": auto, "budget": budget})
        self.store.execute(
            "INSERT OR REPLACE INTO studio_jobs "
            "(world_id, tenant, status, payload, enqueued_at) VALUES (?,?,?,?,?)",
            (world_id, tenant, "queued", payload, self.now()),
        )
        return self.get(world_id)

    def cancel(self, world_id: str) -> bool:
        cursor = self.store.execute(
            "UPDATE studio_jobs SET status='cancelled', finished_at=? "
            "WHERE world_id=? AND status IN ('queued','running')",
            (self.now(), world_id),
        )
        return cursor.rowcount > 0

    # -- workers --------------------------------------------------------

    def recover(self) -> int:
        """Put back jobs whose worker stopped heartbeating. A job that keeps killing workers fails."""
        now = self.now()
        self.store.execute(
            "UPDATE studio_jobs SET status='failed', owner='', "
            "error='gave up after repeated worker failures', finished_at=? "
            "WHERE status='running' AND lease_until < ? AND attempts >= ?",
            (now, now, MAX_ATTEMPTS),
        )
        cursor = self.store.execute(
            "UPDATE studio_jobs SET status='queued', owner='' "
            "WHERE status='running' AND lease_until < ?",
            (now,),
        )
        return cursor.rowcount

    def claim(self, worker: str, *, lease: float = 60.0) -> Job | None:
        """The next job for this worker, or None. Safe to call from many workers at once."""
        self.recover()
        running = self.store.query(
            "SELECT tenant, COUNT(*) AS n FROM studio_jobs WHERE status='running' GROUP BY tenant"
        )
        per_tenant = {r["tenant"]: r["n"] for r in running}
        if sum(per_tenant.values()) >= self.max_running:
            return None
        waiting = self.store.query("SELECT * FROM studio_jobs WHERE status='queued'")
        # Fewest running builds for its tenant first, then the oldest request.
        order = sorted(waiting, key=lambda r: (per_tenant.get(r["tenant"], 0), r["enqueued_at"], r["world_id"]))
        for row in order:
            # The update only wins if the job is still queued: that is the lock.
            cursor = self.store.execute(
                "UPDATE studio_jobs SET status='running', owner=?, lease_until=?, "
                "attempts=attempts+1 WHERE world_id=? AND status='queued'",
                (worker, self.now() + lease, row["world_id"]),
            )
            if cursor.rowcount:
                return self.get(row["world_id"])
        return None

    def heartbeat(self, world_id: str, worker: str, *, lease: float = 60.0) -> bool:
        """Keep the job. False means it was taken away (cancelled, or the lease lapsed)."""
        cursor = self.store.execute(
            "UPDATE studio_jobs SET lease_until=? WHERE world_id=? AND owner=? AND status='running'",
            (self.now() + lease, world_id, worker),
        )
        return cursor.rowcount > 0

    def finish(self, world_id: str, worker: str, *, error: str = "") -> None:
        self.store.execute(
            "UPDATE studio_jobs SET status=?, error=?, finished_at=?, owner='' "
            "WHERE world_id=? AND owner=? AND status='running'",
            ("failed" if error else "done", error[:500], self.now(), world_id, worker),
        )

    # -- readers --------------------------------------------------------

    def get(self, world_id: str) -> Job | None:
        rows = self.store.query("SELECT * FROM studio_jobs WHERE world_id=?", (world_id,))
        return _job(rows[0]) if rows else None

    def all(self, status: str | None = None) -> list[Job]:
        if status:
            rows = self.store.query(
                "SELECT * FROM studio_jobs WHERE status=? ORDER BY enqueued_at", (status,)
            )
        else:
            rows = self.store.query("SELECT * FROM studio_jobs ORDER BY enqueued_at")
        return [_job(r) for r in rows]

    def position(self, world_id: str) -> int | None:
        """Builds ahead of this one in the queue (0: next up). None if it is not waiting."""
        waiting = [j.world_id for j in self.all("queued")]
        return waiting.index(world_id) if world_id in waiting else None
