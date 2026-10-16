import asyncio

from tinyworld.eval.invariants import check_log
from tinyworld.fixtures import toy
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.sim.loop import Simulation


def run(coroutine):
    return asyncio.run(coroutine)


def tool_sim(session, seed="mind"):
    config = LLMConfig()
    llm = StructuredLLM(offline_llm(lambda: session.state, seed=seed), config, Tracer(session.store, config))
    return Simulation(session, llm, resident_tools=True, routines=False, scenes=False)


def test_a_resident_who_deliberates_looks_around_and_then_decides():
    session = toy.build_toy()
    sim = tool_sim(session)
    results = run(sim.run(4))
    roles = [r["role"] for r in session.store.query("SELECT role FROM llm_calls")]
    assert roles.count("agent.mind") >= 6
    looked = session.store.query(
        "SELECT request_json FROM llm_calls WHERE role='agent.mind' AND request_json LIKE '%you used look_around%'"
    )
    assert looked, "the second step should see what look_around returned"
    acted = [e for r in results for e in r.events if e.actor.startswith("person:")]
    assert acted
    assert check_log(session.store, session.branch_id) == []


def test_a_tool_using_world_replays_exactly():
    session = toy.build_toy()
    start = session.state.seq
    run(tool_sim(session).run(3))
    recorded = session.store.events(session.branch_id, after=start)

    replay = session.fork(start, "replay")
    llm = StructuredLLM(ReplayLLM(session.store, session.branch_id), LLMConfig(), Tracer(session.store, LLMConfig()))
    run(Simulation(replay, llm, resident_tools=True, routines=False, scenes=False).run(3))
    replayed = session.store.events(replay.branch_id, after=start)

    def effects(events):
        return [[x.model_dump_json() for x in e.effects] for e in events]

    assert effects(replayed) == effects(recorded)


def test_an_impossible_decision_is_refused_inside_the_session():
    import json

    from tinyworld.agents.toolmind import ToolMind
    from tinyworld.llm.fake import FakeLLM
    from tinyworld.llm.types import CallContext

    session = toy.build_toy()
    steps = iter([
        {"tool": "decide", "args": {"verb": "move", "target": "place:the_moon", "text": "go"}},
        {"tool": "decide", "args": {"verb": "wait", "text": "fine, wait"}},
    ])
    fake = FakeLLM({"agent.mind": lambda r: next(steps), "agent.act": {"verb": "wait"}})
    config = LLMConfig()
    sim = Simulation(session, StructuredLLM(fake, config, Tracer(session.store, config)), resident_tools=True)
    acted = run(ToolMind(sim.agent).act(
        session.state, session.state.entities[toy.ANNA], session.branch_id,
        CallContext(session.branch_id, 1, toy.ANNA), -1,
    ))
    assert acted.ok and acted.intent.verb.value == "wait"
    second = [c for c in fake.calls if c.role == "agent.mind"][1].user
    assert "is not a decision" in second or "cannot be done" in second
