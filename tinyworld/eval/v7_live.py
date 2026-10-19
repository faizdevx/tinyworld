"""A short live run of the town on a real model, with a report of what it did.

    LOCAL_BASE_URL=http://127.0.0.1:8081/v1 LOCAL_CONCURRENCY=1 \\
        python -m tinyworld.eval.v7_live --provider local --hours 4 --residents 5 --db live.sqlite

It lays Falkenrode (the Berlin fixture) out on a tile map, keeps ``--residents`` of the ten people
as deciding residents, lets them live on their own clocks with drives, petitions, fortune and the
paper, and writes down what happened: how lively it was, how often conversations disagreed, what
was asked of the god, which groups were founded, and what the model cost in calls.
"""

import argparse
import asyncio
import json
import time

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy
from tinyworld.core.events import EventDraft
from tinyworld.core.store import Store
from tinyworld.eval import v7_metrics
from tinyworld.eval.v7_experiments import fixture_session
from tinyworld.fixtures import berlin
from tinyworld.llm import ledger
from tinyworld.sim.clock import AsyncSimulation
from tinyworld.sim.loop import Simulation
from tinyworld.sim.town import Town
from tinyworld.studio.creators import Creators, ModelCartographer
from tinyworld.studio.worker import make_provider
from tinyworld.world import institutions, laws, petitions

CAST = ["person:anna_keller", "person:otto_brandt", "person:lena_vogel", "person:friedrich_brandt", "person:hanna_stein",
        "person:ernst_kruger", "person:martin_weiss", "person:greta_lang", "person:karl_hoffmann", "person:dmitri_volkov"]


async def live(provider: str, hours: float, residents: int, db: str | None, chaos: float = 0.3) -> dict:
    store = Store(db) if db else Store()
    session = fixture_session(berlin, store=store)
    keep = set(CAST[:residents])
    # The rest of the town is background until events draw them in.
    session.commit([EventDraft(kind="system", actor="system", visibility="god_only", narration="Only some are deciding.", effects=[
        fx.SetAttr(entity=p.id, key="tier", value=2) for p in session.state.people() if p.id not in keep])])
    make = make_provider(provider)
    llm, _ = make(store, berlin.PREMISE_TEXT)
    digest = "Falkenrode, a small town near Berlin, September 1941. Germany never invaded the USSR."
    sim = Simulation(session, llm, world_digest=digest)
    entropy = Entropy(store, session.branch_id, seq=lambda: session.state.seq)
    clocks = AsyncSimulation(sim, entropy)
    town = Town(sim, entropy, clocks=clocks, drives_on=True, write_petitions=True, noise=True, chaos=chaos,
                creators=Creators(ModelCartographer(llm, digest)))
    started = time.monotonic()
    done = 0
    while done < hours * 60:
        await town.advance(30)
        done += 30
        used = ledger.total(store, session.branch_id, own_only=True)
        print(f"{done / 60:.1f} h simulated, {used.calls} calls, {time.monotonic() - started:.0f} s", flush=True)
    state = session.state
    events = store.events(session.branch_id)
    report = await v7_metrics.report(session, editions=town.editions)
    report["seconds"] = round(time.monotonic() - started)
    report["petitions_filed"] = [
        {"by": state.entities[p.by].name, "kind": p.kind, "text": p.text, "status": p.status, "answer": p.answer}
        for p in petitions.all_petitions(state)
    ]
    report["groups"] = [
        {"name": g.name, "leader": institutions.leader_of(state, g.id), "members": institutions.members(state, g.id)}
        for g in institutions.groups(state)
    ]
    report["laws"] = [f.text for f in laws.laws(state)]
    verbs: dict[str, int] = {}
    for e in events:
        if e.actor.startswith("person:") and e.kind == "action":
            for x in e.effects:
                verbs[type(x).__name__] = verbs.get(type(x).__name__, 0) + 1
    report["effects_by_residents"] = verbs
    report["conversations"] = [
        {"people": [state.entities[p].name for p in c.people if p in state.entities], "lines": [t for _, _, t in c.lines][:4]}
        for c in v7_metrics.conversations(session)[:8]
    ]
    report["papers"] = {d: e.headline for d, e in town.editions.items()}
    report["models_used"] = {m: u.calls for m, u in ledger.by(store, session.branch_id, "model", own_only=True).items()}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="local", choices=["local", "openrouter", "anthropic", "gemini"])
    parser.add_argument("--hours", type=float, default=4)
    parser.add_argument("--residents", type=int, default=5)
    parser.add_argument("--db")
    parser.add_argument("--chaos", type=float, default=0.3)
    parser.add_argument("--json")
    options = parser.parse_args()
    report = asyncio.run(live(options.provider, options.hours, options.residents, options.db, options.chaos))
    text = json.dumps(report, indent=1, default=str)
    print(text)
    if options.json:
        with open(options.json, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
