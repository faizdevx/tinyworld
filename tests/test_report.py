import asyncio

from tinyworld.eval.report import build_report, classify, failure_tag, format_report
from tinyworld.fixtures import toy
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.loop import Simulation


def run(coroutine):
    return asyncio.run(coroutine)


def offline_run(ticks=8):
    session = toy.build_toy()
    config = LLMConfig()
    fake = offline_llm(lambda: session.state, seed="report")
    llm = StructuredLLM(fake, config, Tracer(session.store, config))
    sim = Simulation(session, llm)
    run(sim.run(ticks))
    return session


def test_failure_tags_are_assigned_from_the_reason():
    assert failure_tag("Anna could not do this (go): Otto is not here") == "out_of_reach"
    assert failure_tag("Anna could not do this (go): there is no way to the moon from here") == "unreachable"
    assert failure_tag("Lena could not do this (work): needs 2 people, 1 present") == "blocked"
    assert failure_tag("Lena could not do this (take): no such item") == "unknown_id"
    assert failure_tag("who knows") == "other"


def test_report_counts_actions_calls_and_flags_nothing_on_a_busy_world():
    session = offline_run()
    report = build_report(session.store, session.branch_id, session.state)
    assert report.decisions > 0
    assert sum(report.mix.values()) == report.decisions
    assert report.total_calls > 0
    assert report.simulated_hours > 0
    assert {line.id for line in report.agents} <= {toy.ANNA, toy.OTTO, toy.LENA}
    assert "actions" in format_report(report)


def test_classify_reads_the_effects_of_an_event():
    session = offline_run(6)
    kinds = {classify(e) for e in session.store.events(session.branch_id) if e.kind == "action"}
    assert kinds <= {"move", "speak", "work", "give", "take", "wait", "rest", "other"}


def test_report_warns_about_a_world_where_everyone_waits():
    session = toy.build_toy()
    sim = Simulation(session, None)
    run(sim.run(2))
    report = build_report(session.store, session.branch_id, session.state)
    assert report.decisions == 0
    assert report.warnings == []
