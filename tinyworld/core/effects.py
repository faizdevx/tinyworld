"""The closed vocabulary of state changes.

Reducers exist for exactly these effects. Anything an LLM proposes has to be
expressed with them, which is what keeps model output away from world state.
"""

from typing import Annotated, Literal, Union

from pydantic import Field, JsonValue

from tinyworld.core.ids import EntityId, FactId, ProcessId
from tinyworld.core.state import Commitment, Entity, Fact, Model, PlaceEdge, Process, Region

Channel = Literal["direct", "audible", "public", "written"]
MessageType = Literal[
    "tell", "ask", "answer", "warn", "lie", "gossip",
    "negotiate", "promise", "threaten",
]


class Claim(Model):
    """A statement about the world carried by an utterance. It may be false."""

    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    value: JsonValue = None


class MoveEntity(Model):
    type: Literal["MoveEntity"] = "MoveEntity"
    entity: EntityId
    to: EntityId


class TransferItem(Model):
    type: Literal["TransferItem"] = "TransferItem"
    item: EntityId
    quantity: int = Field(gt=0)
    source: EntityId
    dest: EntityId


class ChangeQuantity(Model):
    """Create or destroy a quantity held by an entity (harvest, consumption)."""

    type: Literal["ChangeQuantity"] = "ChangeQuantity"
    holder: EntityId
    item: EntityId
    delta: int


class SetAttr(Model):
    type: Literal["SetAttr"] = "SetAttr"
    entity: EntityId
    key: str
    value: JsonValue


class CreateEntity(Model):
    type: Literal["CreateEntity"] = "CreateEntity"
    entity: Entity


class RemoveEntity(Model):
    type: Literal["RemoveEntity"] = "RemoveEntity"
    entity: EntityId


class Kill(Model):
    type: Literal["Kill"] = "Kill"
    entity: EntityId
    cause: str = ""


class SetRelation(Model):
    type: Literal["SetRelation"] = "SetRelation"
    source: EntityId
    dest: EntityId
    kind: str = "acquaintance"
    value: int = Field(ge=-100, le=100)
    note: str = ""


class SetEdge(Model):
    """Connect two places, or disconnect them when ``edge`` is None."""

    type: Literal["SetEdge"] = "SetEdge"
    a: EntityId
    b: EntityId
    edge: PlaceEdge | None


class AssertFact(Model):
    type: Literal["AssertFact"] = "AssertFact"
    fact: Fact


class RetractFact(Model):
    type: Literal["RetractFact"] = "RetractFact"
    fact_id: FactId


class StartProcess(Model):
    type: Literal["StartProcess"] = "StartProcess"
    process: Process


class AdvanceProcess(Model):
    type: Literal["AdvanceProcess"] = "AdvanceProcess"
    process_id: ProcessId
    delta: float = Field(ge=-1.0, le=1.0)
    note: str = ""


class EndProcess(Model):
    type: Literal["EndProcess"] = "EndProcess"
    process_id: ProcessId
    status: Literal["completed", "abandoned", "failed"]


class MakeCommitment(Model):
    type: Literal["MakeCommitment"] = "MakeCommitment"
    commitment: Commitment


class ResolveCommitment(Model):
    type: Literal["ResolveCommitment"] = "ResolveCommitment"
    commitment_id: str
    status: Literal["kept", "broken", "released"]


class LearnKnowledge(Model):
    """A person comes to hold an idea. ``by`` says how: study, teach, research, god."""

    type: Literal["LearnKnowledge"] = "LearnKnowledge"
    person: EntityId
    idea: str
    level: int = Field(default=1, ge=1, le=3)
    by: Literal["study", "teach", "research", "god"] = "study"


class Utter(Model):
    """Speech or writing. Changes no state; perception and beliefs read it."""

    type: Literal["Utter"] = "Utter"
    speaker: EntityId
    text: str = Field(min_length=1)
    addressees: list[EntityId] = Field(default_factory=list)
    channel: Channel = "direct"
    message_type: MessageType = "tell"
    claims: list[Claim] = Field(default_factory=list)


class SetRule(Model):
    type: Literal["SetRule"] = "SetRule"
    key: str
    value: JsonValue


class AdvanceTime(Model):
    type: Literal["AdvanceTime"] = "AdvanceTime"
    minutes: int = Field(gt=0)


class Tile(Model):
    x: int
    y: int
    terrain: str = Field(min_length=1, max_length=1)


class SetTiles(Model):
    """Paint terrain and claim rectangles of tiles for places. Chunks appear as they are painted."""

    type: Literal["SetTiles"] = "SetTiles"
    tiles: list[Tile] = Field(default_factory=list, max_length=4096)
    regions: list[Region] = Field(default_factory=list, max_length=256)


class SetPosition(Model):
    """Put a person or thing on a tile. Their place becomes the place that owns the tile."""

    type: Literal["SetPosition"] = "SetPosition"
    entity: EntityId
    x: int
    y: int


Effect = Annotated[
    Union[
        MoveEntity, TransferItem, ChangeQuantity, SetAttr, CreateEntity,
        RemoveEntity, Kill, SetRelation, SetEdge, AssertFact, RetractFact,
        StartProcess, AdvanceProcess, EndProcess, Utter, SetRule, AdvanceTime,
        MakeCommitment, ResolveCommitment, LearnKnowledge, SetTiles, SetPosition,
    ],
    Field(discriminator="type"),
]

EFFECT_TYPES: tuple[str, ...] = (
    "MoveEntity", "TransferItem", "ChangeQuantity", "SetAttr", "CreateEntity",
    "RemoveEntity", "Kill", "SetRelation", "SetEdge", "AssertFact",
    "RetractFact", "StartProcess", "AdvanceProcess", "EndProcess", "Utter",
    "SetRule", "AdvanceTime", "MakeCommitment", "ResolveCommitment",
    "LearnKnowledge", "SetTiles", "SetPosition",
)
