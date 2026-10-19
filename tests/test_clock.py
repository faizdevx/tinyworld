import asyncio
from datetime import timedelta

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy, Fixed
from tinyworld.core.events import EventDraft
from tinyworld.eval.v7_experiments import berlin_session
from tinyworld.fixtures import toy
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.clock import AsyncSimulation
from tinyworld.sim.loop import Simulation
from tinyworld.sim.replay import replay
from tinyworld.sim.town import Town


def run(coroutine):
    return asyncio.run(coroutine)


def build(session=None, entropy=None, handlers=None, **options):
    session = session or toy.build_toy()
    config = LLMConfig()
    fake = offline_llm(lambda: session.state, seed=str(id(session)))
    for role, handler in (handlers or {}).items():
        fake.on(role, handler)
    llm = StructuredLLM(fake, config, Tracer(session.store, config))
    sim = Simulation(session, llm)
    entropy = entropy or Entropy(session.store, session.branch_id, seq=lambda: session.state.seq)
    return AsyncSimulation(sim, entropy, **options), session, fake


def system(session, *effects):
    session.commit([EventDraft(actor="system", effects=list(effects), visibility="god_only")])


# -- optimistic concurrency --------------------------------------------------


def test_a_decision_the_world_has_overtaken_is_decided_again():
    taken = {"n": 0}

    def act(request):
        if "no longer possible" in request.user:
            taken["n"] += 1
            return {"verb": "wait", "text": "the loaf is gone", "args": {"minutes": 30}}
        return {"verb": "take", "target": toy.BAKERY, "args": {"item": toy.BREAD, "quantity": 1}, "text": "take the last loaf"}

    clocks, session, fake = build(handlers={"agent.act": act})
    system(session, fx.ChangeQuantity(holder=toy.BAKERY, item=toy.BREAD, delta=-19),
           fx.MoveEntity(entity=toy.OTTO, to=toy.BAKERY), fx.MoveEntity(entity=toy.LENA, to=toy.FARM))
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.SQUARE))
    # Only Anna and Otto are in the bakery; Lena is elsewhere and takes nothing there.
    run(clocks.step())
    state = session.state
    assert state.entities[toy.BAKERY].inventory.get(toy.BREAD, 0) == 0
    got = [state.entities[p].inventory.get(toy.BREAD, 0) for p in (toy.ANNA, toy.OTTO)]
    assert sum(got) == 2 + 1  # Anna started with 2 loaves; exactly one more was taken
    assert clocks.redecided >= 1 and taken["n"] >= 1


def test_a_decision_still_valid_is_not_redone():
    clocks, session, _ = build(handlers={"agent.act": {"verb": "wait", "text": "wait", "args": {"minutes": 20}}})
    run(clocks.step())
    assert clocks.redecided == 0 and clocks.committed == 3


# -- clocks ------------------------------------------------------------------


def test_each_resident_wakes_when_their_own_action_ends():
    def act(request):
        who = request.context.agent
        minutes = {toy.ANNA: 10, toy.OTTO: 45, toy.LENA: 120}[who]
        return {"verb": "wait", "text": "wait", "args": {"minutes": minutes}}

    clocks, session, _ = build(handlers={"agent.act": act})
    run(clocks.step())
    start = session.state.sim_time
    wakes = {p: clocks.wake[p] - start for p in clocks.wake}
    assert wakes[toy.ANNA] == timedelta(minutes=10)
    assert wakes[toy.OTTO] == timedelta(minutes=45)
    assert wakes[toy.LENA] == timedelta(minutes=120)
    run(clocks.step())
    # The clock moved to the first waking, and only Anna acted.
    assert session.state.sim_time - start == timedelta(minutes=10)
    assert clocks.committed == 4


def test_residents_do_not_act_in_lockstep():
    clocks, session, _ = build()
    run(clocks.run_for(8 * 60))
    times = {}
    for e in session.store.events(session.branch_id):
        if e.actor.startswith("person:") and e.kind in ("action", "utterance"):
            times.setdefault(e.sim_time, set()).add(e.actor)
    assert len({t for t in times}) > 20
    together = sum(1 for who in times.values() if len(who) > 1)
    assert together < len(times) * 0.8


def test_addressing_a_sleeper_wakes_them_now():
    clocks, session, _ = build(handlers={"agent.act": {"verb": "wait", "text": "wait", "args": {"minutes": 600}}})
    run(clocks.step())
    now = session.state.sim_time
    assert clocks.wake[toy.LENA] > now
    clocks.interrupt(toy.LENA, now)
    assert clocks.wake[toy.LENA] == now and clocks.wake[toy.OTTO] > now


def test_a_line_spoken_to_someone_wakes_them():
    def act(request):
        if request.context.agent == toy.ANNA and "no longer" not in request.user:
            return {"verb": "speak", "text": "talk", "say": {"text": "Otto, we must talk.", "to": [toy.OTTO]}}
        return {"verb": "wait", "text": "wait", "args": {"minutes": 600}}

    clocks, session, fake = build(handlers={"agent.act": act})
    system(session, fx.MoveEntity(entity=toy.OTTO, to=toy.BAKERY))
    run(clocks._ensure(session.state) or clocks.step())
    # Otto waits for ten hours, but was spoken to, so he is awake again at once.
    assert clocks.wake[toy.OTTO] <= session.state.sim_time + timedelta(minutes=10)


def test_a_promise_cannot_be_slept_through():
    from datetime import datetime

    from tinyworld.core.state import Commitment

    clocks, session, _ = build(handlers={"agent.act": {"verb": "wait", "text": "sleep", "args": {"minutes": 900}}})
    due = session.state.sim_time + timedelta(hours=5)
    system(session, fx.MakeCommitment(commitment=Commitment(
        id="commitment:meet_otto", by=toy.ANNA, to=toy.OTTO, kind="meet", text="meet",
        due=due, made_at=session.state.sim_time, place=toy.TOWN_HALL)))
    run(clocks.step())
    assert clocks.wake[toy.ANNA] < due


# -- recording ---------------------------------------------------------------


def test_the_order_in_a_window_is_a_recorded_draw():
    clocks, session, _ = build()
    run(clocks.step())
    draws = [r for r in session.store.journal(session.branch_id) if r["op"] == "draw"]
    assert any('"wake.order"' in r["args_json"] for r in draws)


def test_an_asynchronous_run_replays_exactly():
    clocks, session, _ = build()
    run(clocks.run_for(10 * 60))
    report = run(replay(session.store, session.branch_id, LLMConfig()))
    assert report.identical, report.first_difference
    assert report.recorded_events > 30


def test_an_asynchronous_town_with_chance_and_petitions_replays_exactly():
    clocks, session, _ = build()
    town = Town(clocks.sim, clocks.entropy, clocks=clocks, chaos=1.0)
    run(town.advance(14 * 60))
    report = run(replay(session.store, session.branch_id, LLMConfig()))
    assert report.identical, report.first_difference


def test_two_live_runs_from_one_start_diverge_and_both_replay():
    base = toy.build_toy()
    seq = base.state.seq
    a, b = base.fork(seq, "a"), base.fork(seq, "b")
    out = []
    for branch in (a, b):
        clocks, _, _ = build(branch)
        run(clocks.run_for(10 * 60))
        out.append(branch)
    first = [e.narration for e in a.store.events(a.branch_id, after=seq)]
    second = [e.narration for e in b.store.events(b.branch_id, after=seq)]
    assert first != second
    for branch in out:
        report = run(replay(branch.store, branch.branch_id, LLMConfig()))
        assert report.identical, report.first_difference
