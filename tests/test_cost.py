import asyncio
from datetime import timedelta

from tinyworld.eval import crowd
from tinyworld.eval.v7_experiments import town_for
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.mixed import MixedClient
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig, Price
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import CallContext
from tinyworld.sim import cost
from tinyworld.sim.budget import Budget
from tinyworld.sim.clock import AsyncSimulation
from tinyworld.sim.loop import Simulation


def run(c):
    return asyncio.run(c)


def priced():
    config = LLMConfig()
    for model in list(config.prices):
        config.prices[model] = Price(2.0, 10.0, 0.2, 2.5)
    return config


def engine(session, config=None, budget=None, **options):
    config = config or priced()
    fake = offline_llm(lambda: session.state, seed="cost-test")
    llm = StructuredLLM(fake, config, Tracer(session.store, config))
    from tinyworld.core.entropy import Entropy

    sim = Simulation(session, llm, budget=budget, **options)
    return AsyncSimulation(sim, Entropy(session.store, session.branch_id, seq=lambda: session.state.seq)), fake


async def advance_hours(branch, hours, config=None):
    clocks, _ = engine(branch, config)
    await clocks.run_for(int(hours * 60))


def test_the_synthetic_town_has_what_it_says():
    s = crowd.build(12)
    people = s.state.people()
    assert len(people) == 12 and all(p.attrs["persona"]["grudge"] for p in people)
    assert s.state.path("place:house_0", "place:shop_1") is not None


def test_a_cost_estimate_comes_before_the_run_and_is_close():
    config = priced()
    s = crowd.build(10)
    est = run(cost.estimate(s, lambda b, h: advance_hours(b, h, config), residents_target=10, days=1, config=config, probe_hours=24))
    assert est.calls > 50 and est.dollars > 0
    assert "residents for 1 days" in est.say()
    actual = s.fork(s.state.seq, "actual")
    run(advance_hours(actual, 24, config))
    from tinyworld.llm import ledger

    used = ledger.total(actual.store, actual.branch_id, own_only=True)
    assert abs(est.dollars - used.cost) / used.cost < 0.30, (est.dollars, used.cost)
    assert abs(est.calls - used.calls) / used.calls < 0.30, (est.calls, used.calls)


def test_the_estimate_scales_with_people_and_days():
    config = priced()
    s = crowd.build(8)
    one = run(cost.estimate(s, lambda b, h: advance_hours(b, h, config), residents_target=8, days=1, config=config, probe_hours=24))
    many = run(cost.estimate(s, lambda b, h: advance_hours(b, h, config), residents_target=40, days=3, config=config, probe_hours=24))
    assert 10 < many.dollars / one.dollars < 20


def test_a_resident_can_have_a_model_of_their_own():
    s = crowd.build(3)
    config = priced()
    who = s.state.people()[0].id
    config.agent_models[who] = "big-hosted-model"
    assert config.route("agent.act", who).model == "big-hosted-model"
    assert config.route("agent.act", "person:other").model != "big-hosted-model"
    assert config.route("gm.adjudicate", who).model != "big-hosted-model"  # only what they decide
    local, hosted = FakeLLM({"*": {"verb": "wait", "text": "w"}}), FakeLLM({"*": {"verb": "wait", "text": "w"}})
    mixed = MixedClient(local, {"big-hosted-model": hosted})
    llm = StructuredLLM(mixed, config, Tracer(s.store, config))
    from tinyworld.agents.agent import Decision

    for person in s.state.people():
        run(llm.call("agent.act", Decision, system="s", user="u", context=CallContext(s.branch_id, 0, person.id),
                     fallback=Decision(verb="wait")))
    assert len(hosted.calls) == 1 and len(local.calls) == 2
    assert mixed.counts == {"big-hosted-model": 1, config.tiers["standard"]: 2}


def test_under_budget_pressure_the_town_slows_instead_of_overspending():
    config = priced()
    free = crowd.build(8)
    capped = free.fork(free.state.seq, "capped")
    clocks, _ = engine(free, config)
    run(clocks.run_for(8 * 60))
    from tinyworld.llm import ledger

    unconstrained = ledger.total(free.store, free.branch_id, own_only=True)
    budget = cost.DailyBudget(capped.store, capped.branch_id, day_cap=unconstrained.cost * 0.5)
    slow, _ = engine(capped, config, budget=budget)
    run(slow.run_for(8 * 60))
    spent = ledger.total(capped.store, capped.branch_id, own_only=True)
    assert slow.slowed > 0
    assert spent.cost < unconstrained.cost
    assert spent.cost <= budget.day_cap * 1.25


def test_a_spent_budget_stops_the_town():
    config = priced()
    s = crowd.build(6)
    budget = Budget(s.store, s.branch_id, run_cap=0.0005)
    clocks, _ = engine(s, config, budget=budget)
    run(clocks.run_for(12 * 60))
    assert clocks.paused
    assert s.state.sim_time < s.store.initial_state(s.branch_id).sim_time + timedelta(hours=12)
