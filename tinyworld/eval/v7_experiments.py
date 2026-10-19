"""The four Phase 0 experiments of the v7 plan.

    python -m tinyworld.eval.v7_experiments            # scripted stand-in model
    python -m tinyworld.eval.v7_experiments --json out.json

Each answers one go / no-go question on the 10-person Berlin world. With the
scripted stand-in model the numbers show the machinery works and what it
measures; they do not say how interesting a real model's world is. The human
labels the plan asks for (is a run at chaos 0.5 more interesting than at 0?) are
written to a sheet to be filled in, never guessed.
"""

import argparse
import asyncio
import copy
import json
from collections import Counter
from datetime import timedelta

from tinyworld.agents.persona import persona_of
from tinyworld.core.entropy import Entropy
from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.eval import divergence
from tinyworld.fixtures import berlin
from tinyworld.genesis import seeding
from tinyworld.genesis.bible import Bible
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.master import GameMaster
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim import newspaper
from tinyworld.sim.loop import Simulation
from tinyworld.sim.town import Town
from tinyworld.world import petitions


def berlin_session(store: Store | None = None) -> WorldSession:
    store = store or Store()
    bible = Bible.model_validate(
        copy.deepcopy({"premise": berlin.PREMISE, "divergence": berlin.DIVERGENCE, **berlin.SECTIONS})
    )
    drafts, _ = seeding.seed_drafts(bible)
    world = store.create_world("Falkenrode", seeding.start_time(bible))
    session = WorldSession(store, store.create_branch(world, "base", start_time=seeding.start_time(bible)))
    session.commit(drafts)
    return session


def town_for(session: WorldSession, *, chaos: float | None, petitioning=True, paper=True) -> Town:
    """A town whose stand-in model and Game Master both sample from fresh entropy."""
    entropy = Entropy(session.store, session.branch_id, seq=lambda: session.state.seq)
    seed = f"run-{entropy.draw('run.seed'):.12f}"
    config = LLMConfig()
    llm = StructuredLLM(offline_llm(lambda: session.state, seed=seed), config, Tracer(session.store, config))
    gm = GameMaster(Adjudicator(llm), seed=seed)
    sim = Simulation(session, llm, gm=gm)
    return Town(sim, entropy, chaos=chaos, petitioning=petitioning, paper=paper)


async def run_for(town: Town, hours: int, step: int = 60) -> None:
    for _ in range(hours * 60 // step):
        await town.advance(step)


# -- 1. petitions -----------------------------------------------------------


def _words(text: str) -> set[str]:
    return {w.strip(".,;:!?'\"").lower() for w in text.split() if len(w) > 4}


def specificity(state, petition) -> bool:
    """True when the petition shares a content word with its petitioner's goals or fears, and
    more of them than with any other resident's."""
    mine = state.entities[petition.by]
    persona = persona_of(mine)
    own = _words(" ".join((persona.goals + persona.fears) if persona else []))
    if not (_words(petition.text) & own):
        return False
    best_other = 0
    for other in state.people():
        if other.id == petition.by or persona_of(other) is None:
            continue
        p = persona_of(other)
        best_other = max(best_other, len(_words(petition.text) & _words(" ".join(p.goals + p.fears))))
    return len(_words(petition.text) & own) >= best_other


async def experiment_petitions(runs: int = 3, hours: int = 48) -> dict:
    rows = []
    for _ in range(runs):
        session = berlin_session()
        town = town_for(session, chaos=0.5)
        await run_for(town, hours)
        state = session.state
        filed = petitions.all_petitions(state)
        rows.append({
            "petitions": len(filed),
            "residents_who_asked": len({p.by for p in filed}),
            "specific": sum(specificity(state, p) for p in filed),
            "kinds": dict(Counter(p.kind for p in filed)),
            "answers": dict(Counter(p.answer for p in filed if p.answer)),
            "examples": [f"{state.entities[p.by].name}: {p.text}" for p in filed[:3]],
        })
    total = sum(r["petitions"] for r in rows)
    specific = sum(r["specific"] for r in rows)
    return {
        "runs": rows,
        "petitions": total,
        "specific_share": round(specific / total, 3) if total else None,
        "go": bool(total and specific / total >= 0.5),
        "note": "scripted petitions are composed from the person's goals and fears, so specificity "
        "here is by construction; the real test is a model writing them (--provider local).",
    }


# -- 2. chaos dial ----------------------------------------------------------


def non_routine(events) -> int:
    return sum(1 for e in events if e.kind in ("god", "system") and e.narration and "Promoted" not in e.narration
               and "queued" not in e.narration.lower() and e.actor != "gm") + sum(
        1 for e in events if e.kind == "action" and e.effects and any(
            type(x).__name__ in ("TransferItem", "SetRelation", "StartProcess", "Kill") for x in e.effects))


async def experiment_chaos(levels=(0.0, 0.5, 1.0), runs: int = 3, hours: int = 48) -> dict:
    out = {}
    for level in levels:
        sessions, rows = [], []
        for _ in range(runs):
            session = berlin_session()
            town = town_for(session, chaos=level, petitioning=False, paper=False)
            await run_for(town, hours)
            events = session.store.events(session.branch_id)
            fortunes = [e for e in events if e.kind == "system" and e.actor == "system" and e.narration
                        and any(type(x).__name__ in ("SetAttr", "ChangeQuantity", "SetRelation") for x in e.effects)
                        and "Falkenrode" not in e.narration[:0]]
            rows.append({"events": len(events), "non_routine_per_resident_day": round(
                non_routine(events) / (len(session.state.people()) * hours / 24), 3),
                "chance_events": sum(1 for e in events if e.kind == "system" and e.actor == "system"
                                     and e.narration and e.visibility == "public")})
            sessions.append(session)
        spread = divergence.measure(sessions)
        out[str(level)] = {"runs": rows, "outcome_spread": round(spread.outcome_spread, 3),
                           "story_spread": round(spread.story_spread, 3)}
    return {
        "levels": out,
        "labels": "docs/v7_chaos_labels.csv: a reader ranks one run at 0.0 and one at 0.5 "
        "(not done; this needs people)",
        "go": None,
    }


# -- 3. newspaper -----------------------------------------------------------


async def experiment_newspaper(days: int = 3, runs: int = 2) -> dict:
    rows = []
    for _ in range(runs):
        session = berlin_session()
        town = town_for(session, chaos=0.5)
        await run_for(town, days * 24 + 2)
        events = session.store.events(session.branch_id)
        for day, edition in sorted(town.editions.items()):
            todays = newspaper.day_events(events, __import__("datetime").date.fromisoformat(day))
            top = sorted(todays, key=lambda e: (-newspaper.weight(e)[0], e.seq))[:5]
            top = [e for e in top if newspaper.weight(e)[0] >= 3.0]
            cited = {seq for s in edition.stories for seq in s.events}
            rows.append({
                "day": day, "headline": edition.headline, "events_that_day": len(todays),
                "problems": newspaper.check(edition, events),
                "top_events_covered": f"{len([e for e in top if e.seq in cited])}/{len(top)}",
                "covered_share": round(len([e for e in top if e.seq in cited]) / len(top), 3) if top else 1.0,
            })
    share = sum(r["covered_share"] for r in rows) / len(rows) if rows else 0
    return {
        "editions": rows,
        "mean_coverage_of_the_weightiest_events": round(share, 3),
        "invented_events": sum(len(r["problems"]) for r in rows),
        "go": None,
        "note": "coverage and no invented events are measured; whether a reader can name what "
        "happened without the feed needs a reader.",
    }


# -- 4. multiverse x5 -------------------------------------------------------


async def experiment_multiverse(runs: int = 5, hours: int = 48) -> dict:
    base = berlin_session()
    base_seq = base.state.seq
    sessions = []
    for i in range(runs):
        branch = base.fork(base_seq, f"run{i}")
        town = town_for(branch, chaos=0.5)
        await run_for(town, hours)
        sessions.append(branch)
    spread = divergence.measure(sessions, after=base_seq)

    # Differ in who did what, or only in how it was phrased?
    def deeds(s):
        return divergence.story_fingerprint(s.store, s.branch_id, base_seq)

    def phrasing(s):
        return {e.narration for e in s.store.events(s.branch_id, after=base_seq) if e.narration}

    from itertools import combinations

    pairs = list(combinations(range(runs), 2))
    deed_spread = 1 - sum(divergence.similarity(deeds(sessions[a]), deeds(sessions[b])) for a, b in pairs) / len(pairs)
    words_spread = 1 - sum(divergence.similarity(phrasing(sessions[a]), phrasing(sessions[b])) for a, b in pairs) / len(pairs)
    state_marks = [divergence.outcome_fingerprint(s.state) for s in sessions]
    held_everywhere = set.intersection(*state_marks)
    held_somewhere = set.union(*state_marks)
    return {
        "runs": runs,
        "outcome_spread": round(spread.outcome_spread, 3),
        "story_spread": round(spread.story_spread, 3),
        "who_did_what_spread": round(deed_spread, 3),
        "phrasing_spread": round(words_spread, 3),
        "facts_that_differ_between_runs": len(held_somewhere - held_everywhere),
        "facts_in_every_run": len(held_everywhere),
        "go": bool(spread.story_spread > 0.3 and deed_spread > 0.3),
    }


async def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    parser.add_argument("--hours", type=int, default=48)
    options = parser.parse_args(argv)
    report = {
        "petitions": await experiment_petitions(hours=options.hours),
        "chaos": await experiment_chaos(hours=options.hours),
        "newspaper": await experiment_newspaper(),
        "multiverse": await experiment_multiverse(hours=options.hours),
    }
    text = json.dumps(report, indent=1)
    print(text)
    if options.json:
        with open(options.json, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
