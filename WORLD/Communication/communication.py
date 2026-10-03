from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from WORLD.AI.beliefs import Belief
from WORLD.Events.event import EventSource, EventValidationResult, WorldEvent
from WORLD.NPCs.memory import Memory


class MessageType(str, Enum):
    TELL = "tell"
    ASK = "ask"
    ANSWER = "answer"
    WARN = "warn"
    LIE = "lie"
    GOSSIP = "gossip"
    NEGOTIATE = "negotiate"
    PROMISE = "promise"
    THREATEN = "threaten"


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class Message:
    sender: str
    receiver: str
    content: str
    message_type: MessageType | str = MessageType.TELL
    timestamp: tuple[int, int] | None = None
    channel: str = "direct"
    source_reliability: float = 0.5
    claims: Mapping[str, Any] = field(default_factory=dict)
    in_reply_to: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.sender.strip():
            raise ValueError("Message sender cannot be empty.")
        if not self.receiver.strip():
            raise ValueError("Message receiver cannot be empty.")
        if not self.content.strip():
            raise ValueError("Message content cannot be empty.")
        if isinstance(self.message_type, str):
            try:
                object.__setattr__(
                    self,
                    "message_type",
                    MessageType(self.message_type.lower()),
                )
            except ValueError as exc:
                raise ValueError("Unsupported message type.") from exc
        if not isinstance(self.message_type, MessageType):
            raise TypeError("message_type must be a MessageType")
        if not isinstance(self.claims, Mapping):
            raise TypeError("Message claims must be a mapping.")
        object.__setattr__(self, "claims", _freeze(dict(self.claims)))
        if not 0.0 <= self.source_reliability <= 1.0:
            raise ValueError("source_reliability must be between 0.0 and 1.0")


@dataclass(frozen=True)
class MessageProposal:
    sender: str
    receiver: str
    message_type: MessageType | str = MessageType.TELL
    content: str = ""
    timestamp: tuple[int, int] | None = None
    channel: str = "direct"
    source_reliability: float = 0.5
    claims: Mapping[str, Any] = field(default_factory=dict)
    in_reply_to: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.sender.strip():
            raise ValueError("Proposal sender cannot be empty.")
        if not self.receiver.strip():
            raise ValueError("Proposal receiver cannot be empty.")
        if not self.content.strip():
            raise ValueError("Proposal content cannot be empty.")
        if isinstance(self.message_type, str):
            try:
                object.__setattr__(
                    self,
                    "message_type",
                    MessageType(self.message_type.lower()),
                )
            except ValueError as exc:
                raise ValueError("Unsupported message type.") from exc
        if not isinstance(self.message_type, MessageType):
            raise TypeError("message_type must be a MessageType")
        if not isinstance(self.claims, Mapping):
            raise TypeError("Proposal claims must be a mapping.")
        object.__setattr__(self, "claims", _freeze(dict(self.claims)))
        if not 0.0 <= self.source_reliability <= 1.0:
            raise ValueError("source_reliability must be between 0.0 and 1.0")


@dataclass(frozen=True)
class BeliefUpdate:
    source: str
    claim: str
    value: object
    confidence: float = 0.6
    origin_type: str = "communication"

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("Belief source cannot be empty.")
        if not self.claim.strip():
            raise ValueError("Belief claim cannot be empty.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Belief confidence must be between 0 and 1.")


@dataclass(frozen=True)
class CommunicationDeliveryResult:
    success: bool
    validation: EventValidationResult | None = None
    message: Message | None = None
    reason: str = ""
    event: WorldEvent | None = None


class MessageValidator:
    """Validate a message proposal against the authoritative world state."""

    def validate(self, world, proposal: MessageProposal) -> EventValidationResult:
        if not isinstance(proposal, MessageProposal):
            return EventValidationResult(False, "proposal must be a MessageProposal")

        if not proposal.content.strip():
            return EventValidationResult(False, "message content cannot be empty")

        try:
            message_type = MessageType(proposal.message_type.lower())
        except ValueError:
            return EventValidationResult(False, "unsupported message type")

        sender_name = self._normalize_name(proposal.sender)
        receiver_name = self._normalize_name(proposal.receiver)
        sender = self._find_npc(world, sender_name)
        receiver = self._find_npc(world, receiver_name)

        if sender is None:
            return EventValidationResult(False, "sender does not exist")
        if receiver is None:
            return EventValidationResult(False, "receiver does not exist")
        if sender is receiver:
            return EventValidationResult(False, "sender and receiver must differ")

        if proposal.channel not in {"direct", "audible", "public"}:
            return EventValidationResult(False, "unsupported communication channel")

        if proposal.channel == "direct":
            if getattr(sender, "location", None) is None or getattr(receiver, "location", None) is None:
                return EventValidationResult(False, "communication location is required")
            if sender.location != receiver.location:
                observation_system = getattr(world, "observation_system", None)
                if observation_system is None:
                    return EventValidationResult(False, "sender and receiver are not in the same location")
                distance = observation_system.distance(sender.location, receiver.location)
                if distance is None or distance > 1:
                    return EventValidationResult(False, "communication range is invalid")

        return EventValidationResult(
            True,
            "message proposal is valid",
            {
                "sender": sender_name,
                "receiver": receiver_name,
                "message_type": message_type.value,
            },
        )

    @staticmethod
    def _normalize_name(value: str) -> str:
        if value is None:
            return ""
        value = str(value).strip()
        if value.startswith("npc:"):
            return value
        return f"npc:{value}"

    @staticmethod
    def _find_npc(world, name: str):
        for npc in getattr(world, "npcs", []):
            if npc.name == name.removeprefix("npc:"):
                return npc
        return None


class MessageResolver:
    def resolve(self, world, proposal: MessageProposal) -> Message:
        if not isinstance(proposal, MessageProposal):
            raise TypeError("proposal must be a MessageProposal")
        day = getattr(getattr(world, "clock", None), "day", 1)
        hour = getattr(getattr(world, "clock", None), "hour", 0)
        timestamp = proposal.timestamp or (day, hour)
        return Message(
            sender=proposal.sender,
            receiver=proposal.receiver,
            content=proposal.content,
            message_type=proposal.message_type,
            timestamp=timestamp,
            channel=proposal.channel,
            source_reliability=proposal.source_reliability,
            claims=dict(proposal.claims),
            in_reply_to=proposal.in_reply_to,
            conversation_id=proposal.conversation_id,
        )


class CommunicationEngine:
    def __init__(self, validator: MessageValidator | None = None, resolver: MessageResolver | None = None) -> None:
        self.validator = validator or MessageValidator()
        self.resolver = resolver or MessageResolver()

    def deliver(self, world, proposal: MessageProposal) -> CommunicationDeliveryResult:
        validation = self.validator.validate(world, proposal)
        if not validation.success:
            return CommunicationDeliveryResult(False, validation=validation, reason=validation.reason)

        message = self.resolver.resolve(world, proposal)

        receiver = self._find_npc(world, message.receiver)
        if receiver is None:
            return CommunicationDeliveryResult(False, validation=validation, reason="receiver is missing")

        receiver.receive_message(message)

        if hasattr(world, "event_log"):
            world.event_log.add(
                WorldEvent(
                    day=getattr(world.clock, "day", 1),
                    hour=getattr(world.clock, "hour", 0),
                    event_type="communication",
                    actor=message.sender,
                    target=message.receiver,
                    description=f"{message.sender} communicated to {message.receiver}.",
                    properties={
                        "message_type": message.message_type.value,
                        "content": message.content,
                        "channel": message.channel,
                        "claims": dict(message.claims),
                    },
                    consequences=(),
                    cause="communication",
                )
            )

        return CommunicationDeliveryResult(
            True,
            validation=validation,
            message=message,
            reason="message delivered",
            event=getattr(world.event_log, "events", [])[-1] if hasattr(world, "event_log") and world.event_log.events else None,
        )

    @staticmethod
    def _find_npc(world, name: str):
        normalized = str(name).strip()
        if normalized.startswith("npc:"):
            normalized = normalized.removeprefix("npc:")
        for npc in getattr(world, "npcs", []):
            if npc.name == normalized:
                return npc
        return None
