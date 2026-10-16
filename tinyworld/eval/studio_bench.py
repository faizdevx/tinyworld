"""Measure how a studio build went, and compare builds.

    python -m tinyworld.eval.studio_bench                 # the scripted team, 3 premises
    python -m tinyworld.eval.studio_bench --provider openrouter --premise "..."

What it reports, per build:

- first-pass rate: sections accepted on the first attempt, with no rework
- rework rate: fix and revise tasks per section the plan asked for
- blocked rate: tasks that ended blocked
- interventions: questions and permissions the user had to answer
- cost and calls: from the recorded model calls
- draft: sections written and mechanical blocking problems left

The scripted team always scores well. Its numbers show the harness works; only
a real model's numbers say anything about quality, and only when compared with
another model's on the same premises.
"""

import argparse
import asyncio
import json
import time
from datetime import datetime

from tinyworld.core.store import Store
from tinyworld.genesis import critic
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.studio.sim import ScriptedTeam, scripted_search
from tinyworld.studio.state import Studio
from tinyworld.studio.team import Foreman

PREMISES = [
    "What if India never had Jio internet in 2016. Lucknow, Uttar Pradesh.",
    "1941. Germany never invades the USSR. A town near Berlin.",
    "A small trading town in the Silk Road, 1250, where the road is closed.",
]


def measure(studio: Studio, seconds: float | None = None) -> dict:
    tasks = studio.graph.all()
    written = [t for t in tasks if t.kind in ("section", "digest")]
    planned = [t for t in written if t.created_by in ("marlow", "user") and not t.title.startswith(("Fix", "Revise"))]
    rework = [t for t in written if t.title.startswith(("Fix", "Revise"))]
    first_pass = [t for t in planned if t.status == "done" and t.attempts == 0]
    blocked = [t for t in tasks if t.status == "blocked"]
    asked = [d for d in studio.data.decisions if d.kind in ("question", "permission")]
    dollars, calls = studio.spend()
    bible = Foreman._draft_bible_of(studio)
    blocking = [f for f in critic.check(bible) if f.blocking]
    return {
        "goal": studio.data.goal.text if studio.data.goal else "",
        "status": studio.data.goal.status if studio.data.goal else "",
        "tasks": len(tasks),
        "first_pass_rate": round(len(first_pass) / len(planned), 3) if planned else None,
        "rework_rate": round(len(rework) / len(planned), 3) if planned else None,
        "blocked_rate": round(len(blocked) / len(tasks), 3) if tasks else None,
        "interventions": len(asked),
        "cost": round(dollars, 4),
        "calls": calls,
        "sections": len(studio.data.draft),
        "blocking_problems": len(blocking),
        "seconds": round(seconds, 2) if seconds is not None else None,
    }


async def build_once(premise: str, make_llm_and_search) -> dict:
    store = Store()
    world = store.create_world(premise, datetime(2000, 1, 1, 8))
    studio = Studio(store, world)
    llm, search = make_llm_and_search(store, premise)
    foreman = Foreman(studio, llm, search, auto_answer=True)
    started = time.monotonic()
    foreman.submit(premise)
    await foreman.wait()
    return measure(studio, time.monotonic() - started)


async def probe(premise: str, make_llm_and_search, sections=("geography",)) -> dict:
    """A small live check: one research task and a few sections, not a whole build.

    Cheap enough to run on a rate-limited free model, and it exercises the parts
    that matter: the tool loop, the web, notes, and writing a section that must
    pass the real schema.
    """
    store = Store()
    world = store.create_world(premise, datetime(2000, 1, 1, 8))
    studio = Studio(store, world)
    llm, search = make_llm_and_search(store, premise)
    foreman = Foreman(studio, llm, search, auto_answer=True, step_cap=8)
    studio.set_goal(premise)
    research = studio.graph.create(f"Research: {premise[:60]}", kind="research")
    for section in sections:
        studio.graph.create(f"Write {section}", kind="section", section=section, deps=[research.id])
    started = time.monotonic()
    foreman.start()
    await foreman._runner
    out = measure(studio, time.monotonic() - started)
    out["tasks_detail"] = [
        {"title": t.title, "status": t.status, "attempts": t.attempts,
         "reason": t.blocked_reason[:200], "summary": t.summary[:120]}
        for t in studio.graph.all()
    ]
    out["notes"] = [m.title for m in studio.data.memory]
    out["draft"] = {k: (len(v.get("places", [])) if k == "geography" else list(v)[:6])
                    for k, v in studio.data.draft.items()}
    out["feed_tail"] = [f.text[:140] for f in studio.data.feed[-25:]]
    return out


def scripted(store, premise):
    config = LLMConfig()
    return StructuredLLM(ScriptedTeam(), config, Tracer(store, config)), scripted_search(premise)


def summarize(rows: list[dict]) -> dict:
    def mean(key):
        values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        return round(sum(values) / len(values), 3) if values else None

    return {
        "builds": len(rows),
        "merged": sum(1 for r in rows if r["status"] == "merged"),
        **{k: mean(k) for k in (
            "first_pass_rate", "rework_rate", "blocked_rate", "interventions",
            "cost", "calls", "blocking_problems", "seconds",
        )},
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark the studio on a set of premises")
    parser.add_argument("--premise", action="append", help="repeat for several")
    parser.add_argument("--provider", choices=["anthropic", "openrouter", "gemini", "local"])
    parser.add_argument("--probe", action="store_true",
                        help="one research task and one section instead of a whole build")
    parser.add_argument("--sections", nargs="*", default=["geography"])
    options = parser.parse_args(argv)
    premises = options.premise or PREMISES

    if options.provider:
        from tinyworld.api.hub import default_search, make_client

        client = make_client(options.provider)
        if client is None:
            print(f"Could not create a {options.provider} client. Is its key set?")
            return 2

        def real(store, premise):
            config = LLMConfig.load(provider=options.provider)
            return StructuredLLM(client, config, Tracer(store, config)), default_search(True)

        make = real
    else:
        make = scripted

    rows = []
    for premise in premises:
        if options.probe:
            row = await probe(premise, make, tuple(options.sections))
            print(json.dumps(row, indent=1))
            rows.append(row)
            continue
        row = await build_once(premise, make)
        rows.append(row)
        print(json.dumps(row))
    print("summary", json.dumps(summarize(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
