"""Events, and the intent/outcome pair that produces them."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field, JsonValue, field_validator

from tinyworld.core.effects import Channel, Claim, Effect, MessageType
from tinyworld.core.ids import EntityId, parse_id
from tinyworld.core.state import Model

SYSTEM_ACTORS = ("god", "system", "gm")

EventKind = Literal["action", "utterance", "god", "system", "chronicle"]
Visibility = Literal["witnessed", "public", "secret", "god_only"]


class EventDraft(Model):
    """An event before it is committed. The session assigns seq and time."""

    kind: EventKind = "action"
    actor: str
    location: EntityId | None = None
    effects: list[Effect] = Field(default_factory=list)
    narration: str = ""
    causes: list[int] = Field(default_factory=list)
    visibility: Visibility = "witnessed"
    loud: bool = False
    trace_id: str | None = None

    @field_validator("actor")
    @classmethod
    def _valid_actor(cls, actor: str) -> str:
        if actor not in SYSTEM_ACTORS:
            parse_id(actor)
        return actor


class Event(EventDraft):
    branch_id: str
    seq: int = Field(gt=0)
    sim_time: datetime


class Verb(str, Enum):
    MOVE = "move"
    SPEAK = "speak"
    GIVE = "give"
    TAKE = "take"
    TRADE = "trade"
    USE = "use"
    MAKE = "make"
    WORK = "work"
    START = "start"
    REST = "rest"
    ATTACK = "attack"
    WAIT = "wait"
    JOIN = "join"
    LEAVE = "leave"
    PETITION = "petition"
    EXPLORE = "explore"
    OTHER = "other"


class Utterance(Model):
    text: str = Field(min_length=1)
    addressees: list[EntityId] = Field(default_factory=list)
    channel: Channel = "direct"
    message_type: MessageType = "tell"
    claims: list[Claim] = Field(default_factory=list)


class Intent(Model):
    """What an agent is trying to do. The Game Master decides what happens."""

    agent: EntityId
    verb: Verb
    target: str | None = None
    args: dict[str, JsonValue] = Field(default_factory=dict)
    text: str = ""
    utterance: Utterance | None = None


OutcomeStatus = Literal["success", "partial", "failed", "impossible"]


class Outcome(Model):
    intent: Intent
    status: OutcomeStatus
    effects: list[Effect] = Field(default_factory=list)
    narration: str = ""
    reason: str = ""
    minutes: int = 0
    loud: bool = False
    trace_id: str | None = None
