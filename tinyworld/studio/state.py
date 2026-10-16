"""The studio's state: agents, tasks, decisions, memory, feed, and the draft world.

One ``Studio`` per world. Everything in it is saved to the store after each
change, so the foreman can be stopped and started and pick up where it was.
Viewers subscribe to ``bus`` and see every change as a protocol message.
"""

import asyncio
import json
from datetime import datetime

from pydantic import Field

from tinyworld.core.state import Model
from tinyworld.core.store import Store
from tinyworld.studio.protocol import (
    Agent, AuditEntry, Decision, FeedItem, Goal, MemoryEntry, message,
)
from tinyworld.studio.taskgraph import TaskGraph

FEED_LIMIT = 300
MEMORY_LIMIT = 200


class Saved(Model):
    goal: Goal | None = None
    agents: list[Agent] = Field(default_factory=list)
    tasks: list = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    memory: list[MemoryEntry] = Field(default_factory=list)
    feed: list[FeedItem] = Field(default_factory=list)
    # section name -> section JSON. Nothing here is the world until merged.
    draft: dict[str, dict] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)
    merged_version: int | None = None
    # The live world as it was when the goal began, to notice if it moved under us.
    base_hash: str = ""
    base_live: dict[str, dict] = Field(default_factory=dict)
    # The draft is a real bible version: negative, so the world never points at it.
    draft_version: int = 0
    # The last trial run of the draft, shown with the merge.
    trial: dict = Field(default_factory=dict)
    # Web domains the user said "always allow" for, and what the team did outside the draft.
    allowed_domains: list[str] = Field(default_factory=list)
    # How this goal reads the web: ask once (default), all, per_site, none.
    web_mode: str = "ask"
    audit: list[AuditEntry] = Field(default_factory=list)
    # Messages waiting for an agent, delivered at its next step.
    inbox: dict[str, list[str]] = Field(default_factory=dict)
    # The answers given to decisions, in order, so a build can be replayed.
    answers: list[str] = Field(default_factory=list)
    # How many pages and searches each goal may use.
    fetches: int = 0
    searches: int = 0


class Bus:
    """Fan-out of protocol messages to however many viewers are connected."""

    def __init__(self) -> None:
        self.queues: set[asyncio.Queue] = set()

    def subscribe(self, size: int = 1000) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=size)
        self.queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.queues.discard(queue)

    def publish(self, payload: dict) -> None:
        for queue in list(self.queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A viewer this far behind reconnects and reloads the snapshot.
                self.queues.discard(queue)


class Studio:
    def __init__(self, store: Store, world_id: str, *, now=datetime.now) -> None:
        self.store = store
        self.world_id = world_id
        self._now = now
        self.bus = Bus()
        self.data = Saved()
        self.graph = TaskGraph(now=now)
        self._waiters: dict[str, asyncio.Future] = {}
        store.execute(
            "CREATE TABLE IF NOT EXISTS studio_state "
            "(world_id TEXT PRIMARY KEY, json TEXT NOT NULL)"
        )
        self.load()

    # -- persistence ----------------------------------------------------

    def load(self) -> None:
        rows = self.store.query(
            "SELECT json FROM studio_state WHERE world_id=?", (self.world_id,)
        )
        if not rows:
            return
        raw = json.loads(rows[0]["json"])
        from tinyworld.studio.protocol import Task

        raw["tasks"] = [Task.model_validate(t) for t in raw.get("tasks", [])]
        self.data = Saved.model_validate(raw)
        self.graph = TaskGraph(self.data.tasks, now=self._now)
        self.graph._counter = max(
            self.data.counters.get("task", 0), len(self.graph.tasks)
        )
        # Whatever was running when the process stopped is not running now.
        for agent in self.data.agents:
            agent.state, agent.station, agent.activity, agent.task_id = "idle", "lounge", "", None
        for task in self.graph.release_running():
            self.data.feed.append(
                self._item("system", f"{task.title} was interrupted and is back on the wall")
            )
        for decision in self.data.decisions:
            if decision.status == "open" and decision.id not in self._waiters:
                continue  # stays open: the asker is gone, an answer re-queues work

    def save(self) -> None:
        self.data.tasks = self.graph.all()
        self.data.counters["task"] = self.graph._counter
        self.data.feed = self.data.feed[-FEED_LIMIT:]
        self.data.memory = self.data.memory[-MEMORY_LIMIT:]
        self.store.execute(
            "INSERT OR REPLACE INTO studio_state VALUES (?,?)",
            (self.world_id, self.data.model_dump_json()),
        )

    # -- helpers --------------------------------------------------------

    def _next(self, prefix: str) -> str:
        count = self.data.counters.get(prefix, 0) + 1
        self.data.counters[prefix] = count
        return f"{prefix}{count}"

    def _item(self, kind: str, text: str, agent_id: str | None = None) -> FeedItem:
        return FeedItem(
            id=self._next("f"), kind=kind, text=text, agent_id=agent_id, at=self._now()
        )

    def emit(self, kind: str, **payload) -> None:
        self.bus.publish(message(kind, **payload))

    def snapshot(self) -> dict:
        return message(
            "snapshot",
            goal=self.data.goal.model_dump(mode="json") if self.data.goal else None,
            agents=[a.model_dump(mode="json") for a in self.data.agents],
            tasks=[t.model_dump(mode="json") for t in self.graph.all()],
            decisions=[d.model_dump(mode="json") for d in self.data.decisions],
            memory=[m.model_dump(mode="json") for m in self.data.memory],
            feed=[f.model_dump(mode="json") for f in self.data.feed[-80:]],
            draft_sections=sorted(self.data.draft),
        )

    # -- spend, audit, messages ----------------------------------------

    def spend(self) -> tuple[float, int]:
        """(dollars, calls) recorded for this studio."""
        row = self.store.query(
            "SELECT COALESCE(SUM(cost),0) c, COUNT(*) n FROM llm_calls WHERE branch_id=?",
            (self.world_id,),
        )[0]
        return float(row["c"]), int(row["n"])

    def spend_of(self, agent_id: str) -> tuple[float, int]:
        """(dollars, calls) for one agent. Its calls are recorded as ``agent:task``."""
        row = self.store.query(
            "SELECT COALESCE(SUM(cost),0) c, COUNT(*) n FROM llm_calls "
            "WHERE branch_id=? AND (agent=? OR agent LIKE ?)",
            (self.world_id, agent_id, agent_id + ":%"),
        )[0]
        return float(row["c"]), int(row["n"])

    def log(self, actor: str, action: str, detail: str = "") -> AuditEntry:
        entry = AuditEntry(
            id=self._next("a"), actor=actor, action=action, detail=detail[:300],
            at=self._now(),
        )
        self.data.audit.append(entry)
        self.data.audit = self.data.audit[-500:]
        self.emit("audit.add", entry=entry.model_dump(mode="json"))
        return entry

    def send(self, to: str, text: str, sender: str) -> None:
        """Leave a message for an agent. It reads it at its next step, even mid-task."""
        self.data.inbox.setdefault(to, []).append(f"{sender}: {text}")
        self.say(f"to {to}: {text}", None if sender == "you" else sender, "say")
        self.save()

    def take_messages(self, agent_id: str) -> list[str]:
        waiting = self.data.inbox.pop(agent_id, [])
        if waiting:
            self.save()
        return waiting

    # -- goal -----------------------------------------------------------

    def set_goal(self, text: str) -> Goal:
        goal = Goal(id=self._next("g"), text=text, world_id=self.world_id)
        self.data.goal = goal
        self.emit("goal.upsert", goal=goal.model_dump(mode="json"))
        self.save()
        return goal

    def update_goal(self, **fields) -> None:
        if self.data.goal is None:
            return
        for key, value in fields.items():
            setattr(self.data.goal, key, value)
        self.emit("goal.upsert", goal=self.data.goal.model_dump(mode="json"))
        self.save()

    # -- agents ---------------------------------------------------------

    def add_agent(self, agent: Agent) -> Agent:
        self.data.agents = [a for a in self.data.agents if a.id != agent.id] + [agent]
        self.emit("agent.upsert", agent=agent.model_dump(mode="json"))
        self.save()
        return agent

    def agent(self, agent_id: str) -> Agent:
        for agent in self.data.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(agent_id)

    def set_agent(self, agent_id: str, **fields) -> Agent:
        agent = self.agent(agent_id)
        for key, value in fields.items():
            setattr(agent, key, value)
        self.emit("agent.upsert", agent=agent.model_dump(mode="json"))
        self.save()
        return agent

    # -- tasks ----------------------------------------------------------

    def task_changed(self, task_id: str) -> None:
        task = self.graph.get(task_id)
        self.emit("task.upsert", task=task.model_dump(mode="json"))
        if self.data.goal is not None:
            self.data.goal.progress = round(self.graph.progress(), 3)
            self.data.goal.spent = round(self.spend()[0], 6)
            self.emit("goal.upsert", goal=self.data.goal.model_dump(mode="json"))
        self.save()

    # -- feed and memory ------------------------------------------------

    def say(self, text: str, agent_id: str | None = None, kind: str = "say") -> FeedItem:
        item = self._item(kind, text, agent_id)
        self.data.feed.append(item)
        self.emit("feed.add", item=item.model_dump(mode="json"))
        self.save()
        return item

    def remember(self, title: str, body: str, author: str, scope: str = "shared") -> MemoryEntry:
        entry = MemoryEntry(
            id=self._next("m"), scope=scope, title=title.strip()[:120], body=body,
            author=author, updated_at=self._now(),
        )
        # One page per (scope, title): writing again updates it.
        same = [m for m in self.data.memory if m.scope == scope and m.title == entry.title]
        if same:
            entry.id = same[0].id
        self.data.memory = [m for m in self.data.memory if m.id != entry.id] + [entry]
        self.emit("memory.upsert", entry=entry.model_dump(mode="json"))
        self.save()
        return entry

    def forget(self, entry_id: str) -> bool:
        before = len(self.data.memory)
        self.data.memory = [m for m in self.data.memory if m.id != entry_id]
        if len(self.data.memory) == before:
            return False
        self.emit("memory.remove", id=entry_id)
        self.save()
        return True

    def recall(self, agent_id: str, query: str = "", limit: int = 8) -> list[MemoryEntry]:
        words = [w for w in query.lower().split() if len(w) > 2]
        pool = [m for m in self.data.memory if m.scope in ("shared", agent_id)]
        if words:
            def score(m: MemoryEntry) -> int:
                text = (m.title + " " + m.body).lower()
                return sum(w in text for w in words)
            pool = sorted(pool, key=lambda m: -score(m))
        return pool[:limit]

    # -- decisions ------------------------------------------------------

    def ask(self, decision: Decision) -> asyncio.Future:
        """Open a decision and return a future that resolves with the answer."""
        decision.id = self._next("d")
        decision.created_at = self._now()
        decision.status = "open"
        self.data.decisions.append(decision)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiters[decision.id] = future
        self.emit("decision.upsert", decision=decision.model_dump(mode="json"))
        self.say(f"asks: {decision.question}", decision.agent_id, "decision")
        self.save()
        return future

    def open_decisions(self) -> list[Decision]:
        return [d for d in self.data.decisions if d.status == "open"]

    def answer(self, decision_id: str, option: str = "", text: str = "") -> Decision:
        decision = next((d for d in self.data.decisions if d.id == decision_id), None)
        if decision is None:
            raise KeyError(f"no decision {decision_id}")
        if decision.status != "open":
            raise ValueError(f"{decision_id} is already {decision.status}")
        if option and decision.options and option not in decision.options:
            raise ValueError(f"{option!r} is not one of {decision.options}")
        decision.status = "answered"
        decision.answer = option or text
        decision.note = text
        self.data.answers.append(decision.answer)
        self.emit("decision.upsert", decision=decision.model_dump(mode="json"))
        waiter = self._waiters.pop(decision_id, None)
        if waiter is not None and not waiter.done():
            waiter.set_result(decision)
        self.save()
        return decision

    def cancel_decision(self, decision_id: str) -> None:
        for d in self.data.decisions:
            if d.id == decision_id and d.status == "open":
                d.status = "cancelled"
                self.emit("decision.upsert", decision=d.model_dump(mode="json"))
        waiter = self._waiters.pop(decision_id, None)
        if waiter is not None and not waiter.done():
            waiter.cancel()
        self.save()
