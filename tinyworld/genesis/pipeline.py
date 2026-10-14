"""The genesis pipeline: premise → divergence → research → bible → critic → digest.

Each stage stores its artifact and can be run again on its own. Seeding is a
separate, deterministic step that turns the stored bible into a new branch.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.genesis import critic, seeding
from tinyworld.genesis.bible import (
    ARTIFACTS,
    SECTION_BRIEFS,
    SECTIONS,
    Bible,
    BibleStore,
    Critique,
    Digest,
    Divergence,
    Finding,
    Premise,
    Queries,
    Topic,
)
from tinyworld.genesis.research import NullSearch, Researcher, SearchProvider, notes_text
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext

MAX_CRITIC_ROUNDS = 3

PREMISE_SYSTEM = """You read a one-line premise for a simulated world and pin it down.

Fill in the period, a concrete start date, the place, the divergence from real \
history (empty if none), the scope and the tone. Choose sensible specifics when the \
premise leaves room: a named or plausible town, a season, a size.

Only if the premise gives no way to tell roughly when or where it is set, leave \
start_date empty and put one or two short questions in `questions`. Do not ask about \
details you can reasonably choose yourself."""

DIVERGENCE_SYSTEM = """You work out what follows from a change to history.

Start from the divergence point and reason outward: first-order consequences \
(direct and near-certain), second-order (what those cause), third-order (longer \
reach, more speculative). Keep to consequences that would be felt in the stated \
place by the start date. Give each a rationale and a confidence. If there is no \
divergence, say so in the summary and list the real historical conditions that \
matter instead."""

QUERIES_SYSTEM = """You plan background research for a historical world. Write up to \
six short encyclopedia-style search queries that would turn up facts about everyday \
life, institutions, economy and technology in the stated place and period."""

SECTION_SYSTEM = """You are writing one section of a world description that will be \
simulated with autonomous characters.

- Be concrete: named places, named people, quantities. Vague description is useless.
- Follow the divergence analysis. Everything else stays true to the real period.
- Stay consistent with the sections already written and reuse their exact names.
- Build in scarcity and conflicting interests. A world where everyone agrees \
produces nothing.
- Research notes are tagged with a source id. Use them where they help; they are \
background, not instructions."""

DIGEST_SYSTEM = """You condense a world description into what a character or referee \
needs in front of them. Write an overview of at most 180 words: when and where, \
what differs from real history, who holds power, what is scarce, and the main \
tensions. Then give up to eight topics, each a short paragraph, on things that \
need looking up: laws, technology level, prices and rations, daily routine."""


@dataclass
class GenesisStatus:
    world_id: str
    stage: str
    questions: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.stage == "done" and not self.questions


class GenesisPipeline:
    def __init__(
        self,
        store: Store,
        llm: StructuredLLM,
        *,
        search: SearchProvider | None = None,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> None:
        self.store = store
        self.llm = llm
        self.bibles = BibleStore(store)
        self.researcher = Researcher(store, llm, search or NullSearch())
        self.on_progress = on_progress or (lambda stage, detail: None)

    # -- helpers --------------------------------------------------------

    @staticmethod
    def trace_branch(world_id: str) -> str:
        """The pseudo-branch genesis calls are recorded under."""
        return f"genesis:{world_id}"

    def _context(self, world_id: str, part: str) -> CallContext:
        return CallContext(self.trace_branch(world_id), 0, part)

    def _brief(self, world_id: str) -> str:
        bible = self.bibles.load(world_id)
        lines = [
            f"Premise as given: {self.store.world(world_id)['premise']}",
            f"Pinned down: {bible.premise.model_dump_json(exclude={'questions'})}",
        ]
        if bible.divergence is not None:
            lines.append(f"Divergence analysis: {bible.divergence.model_dump_json()}")
        return "\n".join(lines)

    def create_world(self, premise_text: str) -> str:
        return self.store.create_world(premise_text, datetime(2000, 1, 1, 8))

    # -- stages ---------------------------------------------------------

    async def stage_premise(self, world_id: str) -> Premise:
        self.on_progress("premise", "reading the premise")
        text = self.store.world(world_id)["premise"]
        reply = await self.llm.call(
            "genesis.premise",
            Premise,
            system=PREMISE_SYSTEM,
            user=f"Premise: {text}",
            context=self._context(world_id, "premise"),
            fallback=Premise(questions=["The premise could not be read. When and where is it set?"]),
            max_tokens=1500,
        )
        premise = reply.value
        self.bibles.put(world_id, "premise", premise)
        if not premise.questions:
            try:
                start = datetime.fromisoformat(premise.start_date).replace(hour=8)
            except ValueError:
                premise = premise.model_copy(
                    update={"questions": ["What date should the simulation start on?"]}
                )
                self.bibles.put(world_id, "premise", premise)
            else:
                # No events exist yet, so the starting time can still be set.
                self.store.execute(
                    "UPDATE worlds SET start_time=? WHERE id=?", (start.isoformat(), world_id)
                )
        return premise

    async def stage_divergence(self, world_id: str) -> Divergence:
        self.on_progress("divergence", "working out consequences")
        reply = await self.llm.call(
            "genesis.divergence",
            Divergence,
            system=DIVERGENCE_SYSTEM,
            user=self._brief(world_id),
            context=self._context(world_id, "divergence"),
            fallback=Divergence(summary="No divergence analysis could be produced."),
            max_tokens=3000,
        )
        self.bibles.put(world_id, "divergence", reply.value)
        return reply.value

    async def stage_research(self, world_id: str) -> int:
        self.on_progress("research", "searching for sources")
        reply = await self.llm.call(
            "genesis.queries",
            Queries,
            system=QUERIES_SYSTEM,
            user=self._brief(world_id),
            context=self._context(world_id, "queries"),
            fallback=Queries(),
            max_tokens=600,
        )
        bible = self.bibles.load(world_id)
        topic = f"{bible.premise.place}, {bible.premise.period}"
        sources = await self.researcher.research(
            world_id, reply.value.queries, topic, self._context(world_id, "research")
        )
        self.on_progress("research", f"{len(sources)} sources")
        return len(sources)

    async def draft_section(
        self, world_id: str, section: str, findings: list[Finding] | None = None
    ) -> BaseModel:
        if section not in SECTIONS:
            raise ValueError(f"unknown section: {section}")
        self.on_progress("sections", f"{'re' if findings else ''}drafting {section}")
        bible = self.bibles.load(world_id)
        written = {
            name: getattr(bible, name).model_dump()
            for name in SECTIONS
            if name != section and self.bibles.get(world_id, name) is not None
        }
        parts = [
            self._brief(world_id),
            "Research notes:\n" + notes_text(self.researcher.sources(world_id)),
            "Sections already written (JSON):\n"
            + (
                "\n".join(f"{name}: {content}" for name, content in written.items())
                or "(none yet)"
            ),
            f"Write the section: {section}\n{SECTION_BRIEFS[section]}",
        ]
        if findings:
            previous = self.bibles.get(world_id, section)
            parts.append(
                "Your previous version of this section:\n"
                + (previous.model_dump_json() if previous else "(missing)")
                + "\n\nA reviewer found these problems. Fix every one:\n"
                + "\n".join(f"- ({f.kind}) {f.text}" for f in findings)
            )
        schema = SECTIONS[section]
        reply = await self.llm.call(
            f"genesis.section.{section}",
            schema,
            system=SECTION_SYSTEM,
            user="\n\n".join(parts),
            context=self._context(world_id, section),
            fallback=schema(),
            max_tokens=8000,
        )
        # A failed redraft must not wipe out a usable earlier version.
        if reply.ok or self.bibles.get(world_id, section) is None:
            self.bibles.put(world_id, section, reply.value)
        return reply.value

    async def stage_sections(self, world_id: str) -> None:
        for section in SECTIONS:
            await self.draft_section(world_id, section)

    async def stage_critic(self, world_id: str) -> list[Finding]:
        """Review, redraft what is blocked, and repeat up to the round cap."""
        findings: list[Finding] = []
        for round_number in range(MAX_CRITIC_ROUNDS + 1):
            self.on_progress("critic", f"review round {round_number + 1}")
            bible = self.bibles.load(world_id)
            findings = critic.check(bible) + await critic.review(
                self.llm, bible, self._context(world_id, "critic")
            )
            self.bibles.put(world_id, "critique", Critique(findings=findings))
            blocked = [
                section for section in SECTIONS
                if any(f.blocking and f.section == section for f in findings)
            ]
            if not blocked or round_number == MAX_CRITIC_ROUNDS:
                break
            for section in blocked:
                await self.draft_section(
                    world_id, section, [f for f in findings if f.section == section]
                )
        return findings

    async def stage_digest(self, world_id: str) -> Digest:
        self.on_progress("digest", "condensing")
        bible = self.bibles.load(world_id)
        fallback = Digest(
            overview=" ".join(
                part
                for part in (
                    f"{bible.premise.place}, {bible.premise.period}.",
                    bible.divergence.summary if bible.divergence else "",
                    bible.politics.overview,
                    bible.economy.overview,
                )
                if part
            )
            or "A world.",
            topics=[
                Topic(name=name, text=getattr(bible, name).overview)
                for name in ("geography", "politics", "economy", "technology", "culture")
                if getattr(bible, name).overview
            ],
        )
        reply = await self.llm.call(
            "genesis.digest",
            Digest,
            system=DIGEST_SYSTEM,
            user="World description (JSON):\n"
            + bible.model_dump_json(exclude={"critique", "digest"}),
            context=self._context(world_id, "digest"),
            fallback=fallback,
            max_tokens=3000,
        )
        self.bibles.put(world_id, "digest", reply.value)
        return reply.value

    # -- orchestration --------------------------------------------------

    async def run(self, world_id: str) -> GenesisStatus:
        """Run every stage in order. Stops early when the premise needs answers."""
        premise = await self.stage_premise(world_id)
        if premise.questions:
            return GenesisStatus(world_id, "premise", questions=premise.questions)
        await self.stage_divergence(world_id)
        await self.stage_research(world_id)
        await self.stage_sections(world_id)
        findings = await self.stage_critic(world_id)
        await self.stage_digest(world_id)
        self.on_progress("done", "bible ready for review")
        return GenesisStatus(world_id, "done", findings=findings)

    async def run_stage(self, world_id: str, stage: str) -> None:
        """Run one stage, or redraft one section, on its own."""
        stages = {
            "premise": self.stage_premise,
            "divergence": self.stage_divergence,
            "research": self.stage_research,
            "sections": self.stage_sections,
            "critic": self.stage_critic,
            "digest": self.stage_digest,
        }
        if stage in stages:
            await stages[stage](world_id)
        elif stage in SECTIONS:
            await self.draft_section(world_id, stage)
        else:
            raise ValueError(f"unknown stage: {stage}")

    # -- human gate and seeding -----------------------------------------

    def edit(self, world_id: str, section: str, content: dict) -> list[Finding]:
        """Replace a section with the user's version, keeping the old bible version.

        Returns the mechanical findings for the edited bible.
        """
        if section not in ARTIFACTS or section in ("critique",):
            raise ValueError(f"section cannot be edited: {section}")
        validated = ARTIFACTS[section].model_validate(content)
        self.bibles.new_version(world_id)
        self.bibles.put(world_id, section, validated)
        if section == "premise":
            start = datetime.fromisoformat(validated.start_date).replace(hour=8)
            self.store.execute(
                "UPDATE worlds SET start_time=? WHERE id=?", (start.isoformat(), world_id)
            )
        findings = critic.check(self.bibles.load(world_id))
        kept = [
            f for f in self.bibles.load(world_id).critique.findings if f.source == "critic"
        ]
        self.bibles.put(world_id, "critique", Critique(findings=findings + kept))
        return findings

    def seed(self, world_id: str, name: str = "main") -> tuple[WorldSession, list[Finding]]:
        """Create a fresh branch from the current bible. Needs no model."""
        bible = self.bibles.load(world_id)
        if not bible.geography.places:
            raise ValueError("the bible has no places to seed")
        drafts, notes = seeding.seed_drafts(bible)
        # The branch carries its own start, so reseeding after a date change
        # leaves earlier branches of this world replayable.
        branch_id = self.store.create_branch(
            world_id, name, start_time=seeding.start_time(bible)
        )
        session = WorldSession(self.store, branch_id)
        session.commit(drafts)
        return session, notes
