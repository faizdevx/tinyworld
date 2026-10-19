"""The world bible: typed sections that describe a world before it is seeded."""

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from tinyworld.core.state import Model
from tinyworld.core.store import Store

# -- stage 1 and 2 -----------------------------------------------------------


class Premise(Model):
    period: str = ""
    start_date: str = Field(default="", description="ISO date the simulation starts, YYYY-MM-DD")
    place: str = ""
    divergence_point: str = Field(default="", description="What differs from real history, if anything")
    scope: str = Field(default="", description="How large an area and population to simulate")
    tone: str = ""
    constraints: list[str] = Field(default_factory=list)
    questions: list[str] = Field(
        default_factory=list,
        description="Ask these instead of guessing when time or place cannot be fixed",
    )


class Consequence(Model):
    order: Literal[1, 2, 3]
    text: str = Field(min_length=1)
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Divergence(Model):
    summary: str = Field(min_length=1)
    consequences: list[Consequence] = Field(default_factory=list)


# -- stage 4: sections -------------------------------------------------------


class PlaceLink(Model):
    to: str = Field(min_length=1)
    travel_minutes: int = Field(default=5, gt=0)
    visible: bool = False
    audible: bool = False


class PlaceSpec(Model):
    name: str = Field(min_length=1)
    kind: str = "building"
    description: str = ""
    district: str = ""
    enclosed: bool = False
    owner: str = ""
    connects_to: list[PlaceLink] = Field(default_factory=list)


class Geography(Model):
    overview: str = ""
    places: list[PlaceSpec] = Field(default_factory=list)


class Institution(Model):
    name: str = Field(min_length=1)
    kind: str = "institution"
    description: str = ""
    aims: list[str] = Field(default_factory=list)
    leader: str = ""
    members: int = Field(default=0, ge=0)


class Politics(Model):
    overview: str = ""
    institutions: list[Institution] = Field(default_factory=list)
    laws: list[str] = Field(default_factory=list)


class ResourceSpec(Model):
    name: str = Field(min_length=1)
    unit: str = "unit"
    scarcity: str = "normal"
    description: str = ""


class Stock(Model):
    holder: str = Field(min_length=1, description="Name of a place or person")
    resource: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class Economy(Model):
    overview: str = ""
    resources: list[ResourceSpec] = Field(default_factory=list)
    stocks: list[Stock] = Field(default_factory=list)
    scarcities: list[str] = Field(default_factory=list)


class Technology(Model):
    overview: str = ""
    available: list[str] = Field(default_factory=list)
    not_yet: list[str] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(
        default_factory=dict,
        description="For each not_yet item, the available items it builds on",
    )


class PopulationGroup(Model):
    name: str = Field(min_length=1)
    count: int = Field(ge=0)
    description: str = ""
    district: str = ""


class Culture(Model):
    overview: str = ""
    norms: list[str] = Field(default_factory=list)
    daily_life: list[str] = Field(default_factory=list)
    population: list[PopulationGroup] = Field(default_factory=list)


class FactionSpec(Model):
    name: str = Field(min_length=1)
    kind: str = "faction"
    description: str = ""
    aims: list[str] = Field(default_factory=list)
    leader: str = ""
    members: int = Field(default=0, ge=0)
    influence: int = Field(default=50, ge=0, le=100)


class Factions(Model):
    factions: list[FactionSpec] = Field(default_factory=list)


class RelationSpec(Model):
    to: str = Field(min_length=1)
    kind: str = "acquaintance"
    value: int = Field(default=0, ge=-100, le=100)


class FigureSpec(Model):
    name: str = Field(min_length=1)
    age: int = Field(ge=0, le=120)
    occupation: str = ""
    home: str = Field(min_length=1)
    location: str = ""
    faction: str = ""
    summary: str = Field(min_length=1)
    traits: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    # The three edges: one strong opinion, one grudge, one want that gets in someone else's way.
    opinion: str = ""
    grudge: str = ""
    rival_want: str = ""
    speech_style: str = ""
    aptitudes: dict[str, int] = Field(default_factory=dict)
    education: str = ""
    knows: list[str] = Field(default_factory=list)
    does_not_know: list[str] = Field(default_factory=list)
    possessions: list[Stock] = Field(default_factory=list)
    relations: list[RelationSpec] = Field(default_factory=list)


    @field_validator(
        "traits", "values", "goals", "fears", "secrets", "knows", "does_not_know",
        mode="after",
    )
    @classmethod
    def _drop_blank(cls, items: list[str]) -> list[str]:
        # A list of empty strings reads as "present" but says nothing.
        return [item.strip() for item in items if item and item.strip()]


class KeyFigures(Model):
    figures: list[FigureSpec] = Field(default_factory=list)


class Tension(Model):
    text: str = Field(min_length=1)
    parties: list[str] = Field(default_factory=list)
    stakes: str = ""


class Tensions(Model):
    tensions: list[Tension] = Field(default_factory=list)
    starting_facts: list[str] = Field(default_factory=list)


# -- stage 5 and digest ------------------------------------------------------

FindingKind = Literal[
    "contradiction", "anachronism", "unmotivated_change", "gap", "real_person"
]


class Finding(Model):
    kind: FindingKind
    section: str
    text: str = Field(min_length=1)
    blocking: bool = True
    source: Literal["check", "critic"] = "critic"


class Critique(Model):
    findings: list[Finding] = Field(default_factory=list)


class Topic(Model):
    name: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Digest(Model):
    overview: str = Field(min_length=1)
    topics: list[Topic] = Field(default_factory=list)


class Note(Model):
    claim: str = Field(min_length=1)
    source_id: str = ""


class SourceNotes(Model):
    notes: list[Note] = Field(default_factory=list)


class Queries(Model):
    queries: list[str] = Field(default_factory=list, max_length=6)


SECTIONS: dict[str, type[BaseModel]] = {
    "geography": Geography,
    "politics": Politics,
    "economy": Economy,
    "technology": Technology,
    "culture": Culture,
    "factions": Factions,
    "figures": KeyFigures,
    "tensions": Tensions,
}

ARTIFACTS: dict[str, type[BaseModel]] = {
    "premise": Premise,
    "divergence": Divergence,
    **SECTIONS,
    "critique": Critique,
    "digest": Digest,
}

SECTION_BRIEFS = {
    "geography": "The places where the simulation happens and how they connect. "
    "Name 6 to 14 concrete places a person can be in (rooms, buildings, streets, "
    "fields). Every place must connect to at least one other. Mark a place "
    "`enclosed` when what happens inside cannot be seen or heard from outside. "
    "On a link, `visible` and `audible` say whether events carry across it.",
    "politics": "Who holds power here, through which institutions, and the laws "
    "and rules ordinary people actually run into.",
    "economy": "What people live on, what is scarce, and where goods physically "
    "are. Define the resources that matter and place starting stocks at named "
    "places or with named people.",
    "technology": "What is in everyday use, and what does not exist yet. Be "
    "specific to this period and this divergence. In `dependencies`, give each "
    "not-yet item the available items it builds on, using the exact names.",
    "culture": "Norms, daily routines, and who lives here: population groups "
    "with rough counts.",
    "factions": "The organised or informal groups with competing aims.",
    "figures": "8 to 14 individual people who will act on their own. Give each "
    "conflicting goals, real fears and a secret where it fits. Invent every person: "
    "do not use real, living public figures, and use a historical figure only if the "
    "premise names them. Their `home` and "
    "`location` must be places from the geography section, and `faction` a "
    "faction name or empty. `knows` and `does_not_know` bound what this person "
    "could know given their era, class and schooling. Include relations between them.",
    "tensions": "The live conflicts when the simulation starts, and a list of "
    "plain starting facts everyone could know.",
}


class Bible(Model):
    """All artifacts of one bible version, loaded together."""

    premise: Premise = Field(default_factory=Premise)
    divergence: Divergence | None = None
    geography: Geography = Field(default_factory=Geography)
    politics: Politics = Field(default_factory=Politics)
    economy: Economy = Field(default_factory=Economy)
    technology: Technology = Field(default_factory=Technology)
    culture: Culture = Field(default_factory=Culture)
    factions: Factions = Field(default_factory=Factions)
    figures: KeyFigures = Field(default_factory=KeyFigures)
    tensions: Tensions = Field(default_factory=Tensions)
    critique: Critique = Field(default_factory=Critique)
    digest: Digest | None = None

    def world_digest(self) -> str:
        """The compact text agents and the Game Master are given."""
        if self.digest is not None:
            return self.digest.overview
        parts = [self.premise.period, self.premise.place, self.premise.divergence_point]
        return " ".join(part for part in parts if part)


class BibleStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def version(self, world_id: str) -> int:
        return self.store.world(world_id)["bible_version"]

    def put(self, world_id: str, section: str, content: BaseModel) -> None:
        if section not in ARTIFACTS:
            raise ValueError(f"unknown bible section: {section}")
        self.store.execute(
            "INSERT OR REPLACE INTO bible VALUES (?,?,?,?)",
            (world_id, self.version(world_id), section, content.model_dump_json()),
        )

    def put_at(self, world_id: str, version: int, section: str, content: BaseModel) -> None:
        """Write a section at a given version, which need not be the live one.

        Drafts live at negative versions: rows like any other bible, never pointed
        at by the world until a merge copies them into a live version.
        """
        if section not in ARTIFACTS:
            raise ValueError(f"unknown bible section: {section}")
        self.store.execute(
            "INSERT OR REPLACE INTO bible VALUES (?,?,?,?)",
            (world_id, version, section, content.model_dump_json()),
        )

    def get(self, world_id: str, section: str, version: int | None = None):
        version = self.version(world_id) if version is None else version
        rows = self.store.query(
            "SELECT content_json FROM bible WHERE world_id=? AND version=? AND section=?",
            (world_id, version, section),
        )
        if not rows:
            return None
        return ARTIFACTS[section].model_validate_json(rows[0]["content_json"])

    def load(self, world_id: str, version: int | None = None) -> Bible:
        version = self.version(world_id) if version is None else version
        rows = self.store.query(
            "SELECT section, content_json FROM bible WHERE world_id=? AND version=?",
            (world_id, version),
        )
        return Bible.model_validate(
            {row["section"]: json.loads(row["content_json"]) for row in rows}
        )

    def new_version(self, world_id: str) -> int:
        """Copy the current version forward so the previous one stays readable."""
        current = self.version(world_id)
        self.store.execute(
            "INSERT INTO bible (world_id, version, section, content_json)"
            " SELECT world_id, ?, section, content_json FROM bible"
            " WHERE world_id=? AND version=?",
            (current + 1, world_id, current),
        )
        self.store.execute(
            "UPDATE worlds SET bible_version=? WHERE id=?", (current + 1, world_id)
        )
        return current + 1
