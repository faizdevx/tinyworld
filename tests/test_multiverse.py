import asyncio

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy
from tinyworld.core.events import EventDraft
from tinyworld.core.state import Entity
from tinyworld.eval import multiverse
from tinyworld.eval.v7_experiments import fixture_session, town_for
from tinyworld.fixtures import berlin
from tinyworld.sim import years
from tinyworld.sim.town import Town
from tinyworld.sim.tiers import birth_date_for
from tinyworld.world import petitions


def run(c):
    return asyncio.run(c)


def base():
    s = fixture_session(berlin, laid_out=False)
    effects = []
    for name, age in (("Ada Weiss", 22), ("Bruno Weiss", 24), ("Carla Stein", 21), ("Dario Stein", 23)):
        pid = "person:" + name.lower().replace(" ", "_")
        effects.append(fx.CreateEntity(entity=Entity(
            id=pid, kind="person", name=name, location="place:market_square",
            attrs={"age": age, "tier": 0, "birth_date": birth_date_for(s.state.sim_time, age),
                   "persona": {"summary": name, "aptitudes": {"craft": 6}}})))
    for a, b in (("ada_weiss", "bruno_weiss"), ("carla_stein", "dario_stein")):
        effects += [fx.SetRelation(source=f"person:{a}", dest=f"person:{b}", kind="love", value=60),
                    fx.SetRelation(source=f"person:{b}", dest=f"person:{a}", kind="love", value=60)]
    s.commit([EventDraft(actor="system", visibility="god_only", effects=effects)])
    return s


async def advance(branch, index):
    base_town = town_for(branch, chaos=0.5, petitioning=False, paper=False)
    town = Town(base_town.sim, base_town.entropy, paper=False, petitioning=False, chaos=0.5)
    await years.skip(town, 8, town.entropy)


def test_twenty_runs_of_one_world_differ_in_major_outcomes():
    b = base()
    seq = b.state.seq
    runs = run(multiverse.run(b, 20, advance, concurrency=4))
    assert all(r.error == "" for r in runs), [r.error for r in runs if r.error]
    sp = multiverse.spread([r.session for r in runs], after=seq)
    assert sp.runs == 20
    marriages = {k: v for k, v in sp.events.items() if k.startswith("marriage:")}
    deaths = {k: v for k, v in sp.events.items() if k.startswith("death:")}
    assert marriages or deaths
    # At least one major outcome (a death, a marriage, a birth) happens in some runs and not in others.
    assert [k for k in sp.contested if k.startswith(("death:", "marriage:", "birth:", "alive:"))]
    assert sp.headline["story_spread"] > 0.2


def test_the_spread_view_counts_runs_not_stories():
    b = base()
    runs = run(multiverse.run(b, 4, advance, concurrency=2))
    sp = multiverse.spread([r.session for r in runs], after=b.state.seq)
    assert all(0 < v <= 1 for v in sp.alive.values())
    assert sp.petitions["mean"] >= 0
    assert set(sp.as_dict()) >= {"runs", "headline", "alive", "places", "events", "contested"}


def test_a_failed_run_is_kept_and_does_not_lose_the_others():
    b = base()

    async def sometimes(branch, i):
        if i == 1:
            raise RuntimeError("model fell over")
        await advance(branch, i)

    runs = run(multiverse.run(b, 3, sometimes, concurrency=3))
    assert [bool(r.error) for r in runs] == [False, True, False]


def test_any_run_can_be_opened_as_the_main_line():
    b = base()
    runs = run(multiverse.run(b, 2, advance, concurrency=1))
    chosen = runs[1].session
    assert multiverse.pick(b, chosen) == chosen.branch_id
    assert b.store.meta_get(b.world_id, "main_branch") == chosen.branch_id
