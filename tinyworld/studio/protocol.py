"""The studio's wire protocol: what the foreman knows, as typed messages.

The foreman is the source of truth. A viewer connects, receives one
``snapshot``, then a stream of ``*.upsert`` messages, and sends back a few
intents. Nothing here is business logic: these are plain records, so any view
(the web studio, a terminal, a game) can draw them.

Every message on the wire is ``{"v": 1, "type": ..., ...payload}``.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from tinyworld.core.state import Model

PROTOCOL_VERSION = 1

# What an agent is doing, derived from the tools it uses (not self-reported).
AgentState = Literal[
    "idle", "thinking", "researching", "reading", "writing", "reviewing",
    "waiting_user", "blocked", "done", "error",
]
# Where it stands in the studio. A viewer maps these to places.
Station = Literal[
    "lounge", "library", "drafting", "review", "podium", "wall", "web",
]
TaskStatus = Literal["todo", "doing", "review", "done", "blocked", "cancelled"]
TaskKind = Literal["plan", "research", "section", "review", "digest", "custom"]
DecisionKind = Literal["question", "permission", "merge"]
DecisionStatus = Literal["open", "answered", "cancelled"]

MERGE_OPTIONS = ["Merge", "Request changes", "Reject"]
PERMISSION_OPTIONS = ["Allow once", "Always allow", "Deny"]


class Agent(Model):
    id: str
    name: str
    role: str  # lead | researcher | cartographer | historian | economist | caster | critic
    title: str = ""
    color: str = "#888888"
    state: AgentState = "idle"
    station: Station = "lounge"
    activity: str = ""
    task_id: str | None = None
    model: str = ""
    # Steps taken on the current task, and what this agent has cost so far.
    steps: int = 0
    cost: float = 0.0
    calls: int = 0
    active: bool = True
    # A paused agent finishes nothing new: it takes no further task.
    paused: bool = False


class Task(Model):
    id: str
    title: str
    kind: TaskKind = "custom"
    status: TaskStatus = "todo"
    assignee: str | None = None
    deps: list[str] = Field(default_factory=list)
    section: str | None = None
    description: str = ""
    summary: str = ""
    blocked_reason: str = ""
    priority: int = 0
    attempts: int = 0
    created_by: str = "user"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Decision(Model):
    id: str
    agent_id: str
    kind: DecisionKind = "question"
    question: str
    options: list[str] = Field(default_factory=list)
    context: str = ""
    task_id: str | None = None
    status: DecisionStatus = "open"
    answer: str = ""
    # Free text that came with the answer, e.g. what to change.
    note: str = ""
    created_at: datetime | None = None


class MemoryEntry(Model):
    id: str
    scope: str = "shared"  # "shared" or an agent id
    title: str
    body: str
    author: str = ""
    updated_at: datetime | None = None


class FeedItem(Model):
    id: str
    kind: str  # say | tool | task | decision | system
    text: str
    agent_id: str | None = None
    at: datetime | None = None


class Goal(Model):
    id: str
    text: str
    status: Literal[
        "planning", "running", "review", "merged", "rejected", "failed", "paused"
    ] = "planning"
    progress: float = 0.0
    world_id: str = ""
    # Dollars. None means no cap. The team pauses and asks when it is reached.
    budget: float | None = None
    spent: float = 0.0


class AuditEntry(Model):
    """Something with an effect outside the draft: who did it, and what."""

    id: str
    actor: str
    action: str
    detail: str = ""
    at: datetime | None = None


def message(kind: str, **payload) -> dict:
    """A wire message."""
    return {"v": PROTOCOL_VERSION, "type": kind, **payload}
