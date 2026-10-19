"""The multiverse: run one world many times and look at the spread.

``run`` forks N branches from one merged world, gives each fresh entropy, runs
each for the same simulated span (a few at a time, bounded by ``concurrency``
and by the model budget), and returns the sessions. ``spread`` then answers, for
each fact, person and place: *in how many runs does it hold?* Who is alive, who
leads a group, which buildings exist, who petitioned, who married. That is a
distribution of outcomes, not a single story. Any run can be opened as the main
branch to carry on from.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field

from tinyworld.core import effects as fx
from tinyworld.core.session import WorldSession
from tinyworld.eval import divergence
from tinyworld.world import institutions, petitions


@dataclass
class Run:
    index: int
    session: WorldSession
    seconds: float = 0.0
    error: str = ""


async def run(
    base: WorldSession,
    n: int,
    advance,  # async (branch: WorldSession, index: int) -> None, runs one branch to the end
    *,
    concurrency: int = 2,
    name: str = "run",
) -> list[Run]:
    """Fork ``n`` branches at the current head and advance each; failures are kept, not raised."""
    import time

    seq = base.state.seq
    gate = asyncio.Semaphore(max(1, concurrency))
    runs = [Run(i, base.fork(seq, f"{name}{i}")) for i in range(n)]

    async def one(r: Run) -> None:
        async with gate:
            started = time.monotonic()
            try:
                await advance(r.session, r.index)
            except Exception as exc:  # noqa: BLE001 - one bad run must not lose the others
                r.error = repr(exc)
            r.seconds = round(time.monotonic() - started, 2)

    await asyncio.gather(*(one(r) for r in runs))
    return runs


@dataclass
class Spread:
    runs: int
    headline: dict
    alive: dict[str, float] = field(default_factory=dict)
    leaders: dict[str, dict[str, float]] = field(default_factory=dict)
    places: dict[str, float] = field(default_factory=dict)
    events: dict[str, float] = field(default_factory=dict)
    petitions: dict = field(default_factory=dict)
    contested: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__ | {}


def _share(counter: Counter, runs: int) -> dict[str, float]:
    return {k: round(v / runs, 3) for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))}


def spread(sessions: list[WorldSession], after: int = 0) -> Spread:
    """For each thing that can differ, the share of runs in which it holds."""
    n = len(sessions)
    head = divergence.measure(sessions, after=after).as_dict() if n >= 2 else {}
    alive: Counter = Counter()
    leaders: dict[str, Counter] = {}
    places: Counter = Counter()
    kinds: Counter = Counter()
    petitioners: Counter = Counter()
    counts = []
    for s in sessions:
        st = s.state
        for p in st.people(alive=False):
            if p.alive:
                alive[p.id] += 1
        for g in institutions.groups(st):
            lead = institutions.leader_of(st, g.id)
            if lead and institutions.members(st, g.id):
                leaders.setdefault(g.id, Counter())[lead] += 1
            places[f"group:{g.id}"] += 1 if institutions.members(st, g.id) else 0
        for e in st.entities.values():
            if e.kind == "place" and not e.id.startswith(("place:blk_", "place:wild_")):
                places[e.id] += 1
        seen = set()
        for ev in s.store.events(s.branch_id, after=after):
            for x in ev.effects:
                if isinstance(x, fx.Kill):
                    seen.add(f"death:{x.entity}")
                elif isinstance(x, fx.SetRelation) and x.kind == "spouse" and x.value > 0:
                    seen.add("marriage:" + "+".join(sorted((x.source, x.dest))))
                elif isinstance(x, fx.CreateEntity) and x.entity.kind == "person" and ev.actor == "system" and "born" in ev.narration:
                    seen.add(f"birth:{x.entity.id}")
                elif isinstance(x, fx.CreateEntity) and x.entity.kind in ("org", "faction"):
                    seen.add(f"founding:{x.entity.id}")
        for k in seen:
            kinds[k] += 1
        ps = petitions.all_petitions(st)
        counts.append(len(ps))
        for who in {p.by for p in ps}:
            petitioners[who] += 1
    out = Spread(
        runs=n, headline=head, alive=_share(alive, n),
        leaders={g: _share(c, n) for g, c in leaders.items()},
        places={k: v for k, v in _share(places, n).items()},
        events=_share(kinds, n),
        petitions={
            "per_run": counts,
            "mean": round(sum(counts) / n, 2) if n else 0,
            "who_asked": _share(petitioners, n),
        },
    )
    # What is not the same in every run: where the interesting questions are.
    everything = {**{f"alive:{k}": v for k, v in out.alive.items()}, **{f"place:{k}": v for k, v in out.places.items()}, **out.events}
    out.contested = sorted(k for k, v in everything.items() if 0 < v < 1)
    return out


def pick(base: WorldSession, chosen: WorldSession, name: str = "main") -> str:
    """Make a run the world's main line to carry on from: a new root view of that branch."""
    store = base.store
    store.meta_set(base.world_id, "main_branch", chosen.branch_id)
    return chosen.branch_id
