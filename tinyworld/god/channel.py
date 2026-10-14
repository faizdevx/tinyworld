"""The god channel: text in, a verdict with a reason out, and events if it applies."""

from pydantic import Field

from tinyworld.core.reducers import EffectError, apply_event_in_place, end_time
from tinyworld.core.events import Event
from tinyworld.core.ids import make_id
from tinyworld.core.session import CommitError, WorldSession
from tinyworld.core.state import Model
from tinyworld.god import compiler
from tinyworld.god.feasibility import Judgement, Verdict, judge, overall
from tinyworld.god.parser import GodCommand, GodParser, Parsed
from tinyworld.gm.perception import Observation, perceive
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext
from tinyworld.sim.schedule import Scheduler


class GodResult(Model):
    text: str
    verdict: Verdict | str
    explanation: str
    question: str = ""
    judgements: list[Judgement] = Field(default_factory=list)
    event_seqs: list[int] = Field(default_factory=list)
    scheduled: list[str] = Field(default_factory=list)
    fork_seq: int | None = None
    branch_id: str = ""

    @property
    def applied(self) -> bool:
        return self.verdict in ("apply", "apply_adjusted")


class GodChannel:
    def __init__(self, llm: StructuredLLM | None, *, world_digest: str = "") -> None:
        self.llm = llm
        self.world_digest = world_digest
        self.parser = GodParser(llm, world_digest=world_digest) if llm else None
        # Observations from the latest applied command, for the caller to hand
        # to whoever keeps agents' memories.
        self.last_observations: list[Observation] = []

    async def submit(self, session: WorldSession, text: str) -> GodResult:
        """Parse, judge and, when feasible, apply what the god said."""
        if self.parser is None:
            return GodResult(
                text=text, verdict="reject", branch_id=session.branch_id,
                explanation="No model is configured to read free-text commands.",
            )
        context = CallContext(session.branch_id, session.state.seq)
        parsed: Parsed = await self.parser.parse(session.state, text, context)
        if parsed.question or not parsed.commands:
            return GodResult(
                text=text, verdict="question", branch_id=session.branch_id,
                explanation="This needs clarifying before anything is changed.",
                question=parsed.question or "What exactly should happen?",
            )
        return await self.apply(session, text, parsed.commands)

    def _judge_all(self, session: WorldSession, commands: list[GodCommand]) -> list[Judgement]:
        pending: set[str] = set()
        judgements = []
        for command in commands:
            judgement = judge(
                session.state, command, registry=session.registry, pending_places=pending
            )
            judgements.append(judgement)
            if command.op == "spawn" and command.kind == "place" and command.name:
                try:
                    pending.add(make_id("place", command.name))
                except ValueError:
                    pass
        return judgements

    async def apply(
        self, session: WorldSession, text: str, commands: list[GodCommand]
    ) -> GodResult:
        """Judge and apply already-parsed commands as one all-or-nothing request."""
        self.last_observations = []
        judgements = self._judge_all(session, commands)
        verdict = overall(judgements)
        result = GodResult(
            text=text, verdict=verdict, judgements=judgements,
            branch_id=session.branch_id,
            explanation=" ".join(
                j.explanation for j in judgements if j.verdict == verdict
            ),
        )
        if verdict == "reject":
            return result
        if verdict == "needs_fork":
            earliest = min(j.when for j in judgements if j.verdict == "needs_fork")
            result.fork_seq = self.seq_at(session, earliest)
            return result

        context = CallContext(session.branch_id, session.state.seq)
        scheduler = Scheduler(session.store)
        # Commands are compiled one after another against a preview state, so a
        # later command can refer to what an earlier one creates.
        preview = session.state.model_copy(deep=True)
        now_drafts = []
        later = []
        notes = []
        try:
            for judgement in judgements:
                profile = None
                command = judgement.command
                if command.op == "spawn" and command.kind == "person":
                    profile = await compiler.build_profile(
                        self.llm, preview, command, context, self.world_digest
                    )
                    notes.append(profile.explanation)
                drafts = compiler.compile_command(preview, judgement, profile)
                if judgement.when is not None:
                    later += [(judgement.when, draft) for draft in drafts]
                    continue
                for draft in drafts:
                    apply_event_in_place(
                        preview,
                        Event(
                            **draft.model_dump(), branch_id=session.branch_id,
                            seq=preview.seq + 1,
                            sim_time=end_time(preview, draft.effects),
                        ),
                        session.registry,
                    )
                    now_drafts.append(draft)
            committed = session.commit(now_drafts, observe=perceive)
        except (EffectError, CommitError, KeyError, ValueError) as exc:
            result.verdict = "reject"
            result.explanation = f"The world cannot take this change: {exc}"
            return result

        result.event_seqs = [event.seq for event in committed.events]
        self.last_observations = [o for batch in committed.observed for o in batch]
        for when, draft in later:
            result.scheduled.append(
                scheduler.add(session.branch_id, session.state.seq, when, draft)
            )
        extra = " ".join(note for note in notes if note)
        if extra:
            result.explanation = f"{result.explanation} {extra}".strip()
        return result

    @staticmethod
    def seq_at(session: WorldSession, when) -> int:
        """The last event at or before ``when``: where a retroactive change forks."""
        return session.store.seq_at_time(session.branch_id, when)

    async def apply_in_fork(
        self, session: WorldSession, result: GodResult, name: str = "what-if"
    ) -> tuple[WorldSession, GodResult]:
        """Carry out a ``needs_fork`` result on a new branch split at that moment."""
        if result.verdict != "needs_fork" or result.fork_seq is None:
            raise ValueError("this result does not ask for a fork")
        fork = session.fork(result.fork_seq, name)
        commands = [
            j.command.model_copy(update={"when": ""})
            if j.verdict == "needs_fork"
            else j.command
            for j in result.judgements
        ]
        applied = await self.apply(fork, result.text, commands)
        return fork, applied
