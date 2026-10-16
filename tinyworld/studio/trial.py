"""A trial run of a draft world before it is merged: the studio's CI.

AgentCraft runs your tests after each task and shows the result in the review.
A world has no test suite, but it can be tried: seed the draft into a scratch
store, run it for a while, and check that nothing breaks. The scratch store is
thrown away; the live world is never touched.

The trial uses the rule-driven stand-in for the residents, so it costs nothing
and finishes in seconds. It proves the world is *runnable* (places connect,
people have homes, nothing violates an invariant), not that it is interesting.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.eval import invariants
from tinyworld.genesis import seeding
from tinyworld.genesis.bible import Bible
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.loop import Simulation


@dataclass
class TrialReport:
    ok: bool
    ticks: int = 0
    events: int = 0
    people: int = 0
    acted: int = 0
    places: int = 0
    problems: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)

    def line(self) -> str:
        if not self.ok:
            return "Trial run failed: " + "; ".join(self.problems[:3])
        return (
            f"Trial run: {self.ticks} steps, {self.events} events, {self.acted} of "
            f"{self.people} people acted, {len(self.problems)} problems"
            + (f", {len(self.repairs)} repairs at seeding" if self.repairs else "")
        )

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "ticks": self.ticks, "events": self.events,
            "people": self.people, "acted": self.acted, "places": self.places,
            "problems": self.problems, "repairs": self.repairs, "summary": self.line(),
        }


async def trial(bible: Bible, *, ticks: int = 12, goal: str = "trial") -> TrialReport:
    """Seed ``bible`` in a throwaway store and run it with rule-driven residents."""
    if not bible.geography.places:
        return TrialReport(False, problems=["the draft has no places"])
    try:
        start = seeding.start_time(bible)
    except ValueError:
        start = datetime(2000, 1, 1, 8)
    store = Store()
    world = store.create_world(goal, start)
    branch = store.create_branch(world, "trial", start_time=start)
    session = WorldSession(store, branch)
    try:
        drafts, notes = seeding.seed_drafts(bible)
        session.commit(drafts)
    except Exception as exc:  # a draft that cannot even be seeded is the finding
        return TrialReport(False, problems=[f"seeding failed: {type(exc).__name__}: {exc}"])
    report = TrialReport(True, repairs=[n.text for n in notes])
    structural = seeding.check_world(session.state)
    report.problems += structural
    config = LLMConfig()
    llm = StructuredLLM(
        offline_llm(lambda: session.state, seed="trial"), config, Tracer(store, config)
    )
    sim = Simulation(session, llm)
    before = session.state.seq
    try:
        results = await sim.run(ticks)
    except Exception as exc:
        report.ok = False
        report.problems.append(f"the world stopped running: {type(exc).__name__}: {exc}")
        return report
    report.ticks = len(results)
    events = store.events(branch, after=before)
    report.events = len(events)
    people = [p for p in session.state.people() if p.attrs.get("persona")]
    report.people = len(people)
    report.acted = len({e.actor for e in events if e.actor.startswith("person:")})
    report.places = sum(1 for e in session.state.entities.values() if e.kind == "place")
    violations = invariants.check_log(store, branch)
    report.problems += [str(v) for v in violations[:5]]
    if violations or structural:
        report.ok = False
    return report


def run_trial(bible: Bible, ticks: int = 12) -> TrialReport:
    return asyncio.run(trial(bible, ticks=ticks))
