"""How differently the same premise plays out across runs.

A world that tells the same story every time is not simulating anything. This
compares runs by what ended up true in each, and by what happened on the way.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from itertools import combinations

from tinyworld.core.session import WorldSession
from tinyworld.core.state import WorldState
from tinyworld.core.store import Store

COLLAPSE_BELOW = 0.15


def outcome_fingerprint(state: WorldState) -> set[str]:
    """What is true at the end, as comparable statements."""
    marks: set[str] = set()
    for person in state.people(alive=False):
        marks.add(f"{person.id}:alive={person.alive}")
        marks.add(f"{person.id}:at={person.location}")
    for key, relation in state.relations.items():
        leaning = "warm" if relation.value > 20 else "cold" if relation.value < -20 else "neutral"
        marks.add(f"{key}:{leaning}")
    for fact in state.active_facts():
        marks.add(f"fact:{fact.id}")
    for process in state.processes.values():
        marks.add(f"{process.id}:{process.status}")
    for entity in state.entities.values():
        for item, quantity in entity.inventory.items():
            marks.add(f"{entity.id}:has:{item}:{'some' if quantity else 'none'}")
    return marks


def story_fingerprint(store: Store, branch_id: str, after: int = 0) -> set[str]:
    """What happened, reduced to who did which kind of thing to whom."""
    marks: set[str] = set()
    for event in store.events(branch_id, after=after):
        if event.actor in ("system",):
            continue
        for effect in event.effects:
            target = (
                getattr(effect, "to", None)
                or getattr(effect, "dest", None)
                or getattr(effect, "entity", None)
                or ",".join(getattr(effect, "addressees", []))
            )
            if isinstance(target, str) or target is None:
                marks.add(f"{event.actor}|{effect.type}|{target}")
        if not event.effects and event.kind in ("chronicle", "god"):
            marks.add(f"{event.actor}|{event.narration}")
    return marks


def similarity(first: set[str], second: set[str]) -> float:
    if not first and not second:
        return 1.0
    return len(first & second) / len(first | second)


@dataclass
class Spread:
    runs: int
    outcome_spread: float
    story_spread: float
    collapsed: bool

    def as_dict(self) -> dict:
        return {
            "runs": self.runs,
            "outcome_spread": round(self.outcome_spread, 3),
            "story_spread": round(self.story_spread, 3),
            "collapsed": self.collapsed,
        }


def measure(sessions: list[WorldSession], after: int = 0) -> Spread:
    """Spread across finished runs: 0 means identical, 1 means nothing in common."""
    if len(sessions) < 2:
        raise ValueError("at least two runs are needed to measure spread")
    outcomes = [outcome_fingerprint(s.state) for s in sessions]
    stories = [story_fingerprint(s.store, s.branch_id, after) for s in sessions]
    pairs = list(combinations(range(len(sessions)), 2))
    outcome = 1 - sum(similarity(outcomes[a], outcomes[b]) for a, b in pairs) / len(pairs)
    story = 1 - sum(similarity(stories[a], stories[b]) for a, b in pairs) / len(pairs)
    return Spread(len(sessions), outcome, story, collapsed=story < COLLAPSE_BELOW)


async def run_many(
    start: Callable[[int], Awaitable[WorldSession]], runs: int
) -> Spread:
    """Run ``start(index)`` for each run and measure the spread of the results.

    ``start`` builds one world, runs it as long as it likes, and returns its
    session. Each run must begin from the same seeded state.
    """
    sessions = [await start(index) for index in range(runs)]
    return measure(sessions)
