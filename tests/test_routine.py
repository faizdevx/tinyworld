import asyncio
import re
from datetime import datetime, timedelta

from tinyworld.agents import routine as daily
from tinyworld.agents.memory import NewMemory
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.fixtures import toy
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.sim.loop import Simulation


def run(coroutine):
    return asyncio.run(coroutine)


def llm_for(session, fake):
    return StructuredLLM(fake, LLMConfig(), Tracer(session.store, LLMConfig()))


def commit(session, *effects):
    session.commit([EventDraft(actor="system", effects=list(effects), visibility="god_only")])


def lived_in(session, wage=6):
    """Give the toy people homes and workplaces, and a wage."""
    commit(
        session,
        fx.SetAttr(entity=toy.ANNA, key="home", value=toy.BAKERY),
        fx.SetAttr(entity=toy.ANNA, key="workplace", value=toy.BAKERY),
        fx.SetAttr(entity=toy.OTTO, key="home", value=toy.TAVERN),
        fx.SetAttr(entity=toy.OTTO, key="workplace", value=toy.TOWN_HALL),
        fx.SetAttr(entity=toy.LENA, key="home", value=toy.FARM),
        fx.SetAttr(entity=toy.LENA, key="workplace", value=toy.BAKERY),
        fx.SetRule(key="wage", value={"item": toy.COIN, "per_hour": wage}),
    )
    return session


def quiet_llm():
    def importance(request):
        return {"scores": [3] * len(re.findall(r"^\d+\. ", request.user, re.MULTILINE))}

    return FakeLLM(
        {
            "agent.act": {"verb": "wait", "text": "wait"},
            "memory.importance": importance,
            "agent.reflect": {"insights": [], "beliefs": []},
            "memory.summarize": {"text": "Earlier days.", "importance": 2},
        }
    )


def acting(fake):
    return [c for c in fake.calls if c.role.startswith("agent.act")]


def at(hour):
    return datetime(1943, 3, 15, hour, 0)


def test_the_day_has_sleep_a_morning_work_and_free_evenings():
    session = lived_in(toy.build_toy())
    state = session.state
    anna = state.entities[toy.ANNA]
    assert daily.current_block(state, anna, at(3)).kind == "sleep"
    assert daily.current_block(state, anna, at(3)).until == at(6)
    assert daily.current_block(state, anna, at(23)).until == at(6) + timedelta(days=1)
    assert daily.current_block(state, anna, at(7)).kind == "morning"
    assert daily.current_block(state, anna, at(10)).kind == "work"
    assert daily.current_block(state, anna, at(10)).place == toy.BAKERY
    assert daily.current_block(state, anna, at(19)) is None


def test_people_without_a_home_have_no_routine():
    session = toy.build_toy()
    state = session.state
    assert daily.current_block(state, state.entities[toy.ANNA], at(10)) is None
    assert daily.hint(state, state.entities[toy.ANNA], None) == ""


def test_routine_hours_come_from_the_world_rules():
    session = lived_in(toy.build_toy())
    commit(session, fx.SetRule(key="day", value={"work_start": 5, "wake": 4}))
    block = daily.current_block(session.state, session.state.entities[toy.ANNA], at(6))
    assert block.kind == "work"


def test_a_workday_runs_on_routine_with_no_model_calls_and_pays_wages():
    session = lived_in(toy.build_toy())
    fake = quiet_llm()
    sim = Simulation(session, llm_for(session, fake), deliberate_hours=48)
    run(sim.tick(60))  # first look: everyone decides afresh
    before = len(acting(fake))
    assert before == 3
    coins = session.state.entities[toy.ANNA].inventory[toy.COIN]

    result = run(sim.tick(60))
    assert len(acting(fake)) == before
    assert set(result.modes.values()) == {"routine"}
    assert result.routine == 3
    narrations = [e.narration for e in result.events if e.actor == toy.ANNA]
    assert narrations == ["Anna Keller works at Keller Bakery."]
    assert session.state.entities[toy.ANNA].inventory[toy.COIN] == coins + 6


def test_a_routine_moves_people_to_where_they_should_be():
    session = lived_in(toy.build_toy())
    sim = Simulation(session, llm_for(session, quiet_llm()), deliberate_hours=48)
    run(sim.tick(60))
    run(sim.tick(60))
    assert session.state.entities[toy.OTTO].location == toy.TOWN_HALL
    assert session.state.entities[toy.LENA].location == toy.BAKERY


def test_something_important_hands_the_decision_back_to_the_model():
    session = lived_in(toy.build_toy())
    sim = Simulation(session, llm_for(session, quiet_llm()), deliberate_hours=48)
    run(sim.tick(60))
    assert sim.mode_of(session.state.entities[toy.ANNA])[0] == "routine"
    sim.memory.write(
        session.branch_id, toy.ANNA,
        [
            NewMemory(
                kind="observation", text="Soldiers are taking the flour.",
                created_seq=session.state.seq + 1, sim_time=session.state.sim_time,
                importance=0.9,
            )
        ],
    )
    assert sim.mode_of(session.state.entities[toy.ANNA])[0] == "react"
    result = run(sim.tick(60))
    assert result.modes[toy.ANNA] == "react"


def test_a_person_stuck_repeating_themselves_is_asked_to_decide_again():
    session = lived_in(toy.build_toy())
    sim = Simulation(session, llm_for(session, quiet_llm()), deliberate_hours=48)
    run(sim.tick(60))
    assert sim.mode_of(session.state.entities[toy.ANNA])[0] == "routine"
    for _ in range(3):
        session.commit(
            [
                EventDraft(
                    kind="action", actor=toy.ANNA, location=toy.BAKERY,
                    narration="Anna Keller waits.",
                )
            ]
        )
    assert sim.mode_of(session.state.entities[toy.ANNA])[0] == "deliberate"
    prompt = sim.agent._prompt(
        session.state, session.state.entities[toy.ANNA],
        __import__("tinyworld.agents.persona", fromlist=["persona_of"]).persona_of(
            session.state.entities[toy.ANNA]
        ),
        session.branch_id, -1, recent=sim.recent_actions(toy.ANNA),
    )[0]
    assert "same thing several times" in prompt


def test_a_quiet_night_is_one_long_step():
    session = lived_in(toy.build_toy())
    sim = Simulation(session, llm_for(session, quiet_llm()), deliberate_hours=48)
    run(sim.tick(60))
    commit(session, fx.AdvanceTime(minutes=14 * 60))  # to 23:00
    assert session.state.sim_time.hour == 23
    run(sim.tick(60))  # everyone goes home and goes to sleep
    result = run(sim.tick())
    assert result.step_minutes > 60
    assert session.state.sim_time.hour == 6 or session.state.sim_time.hour < 8
    assert set(result.modes.values()) == {"routine"}


def test_free_time_is_left_to_the_model_every_step():
    session = lived_in(toy.build_toy())
    fake = quiet_llm()
    sim = Simulation(session, llm_for(session, fake), deliberate_hours=48)
    run(sim.tick(60))
    commit(session, fx.AdvanceTime(minutes=10 * 60))  # to 19:00
    before = len(acting(fake))
    result = run(sim.tick(60))
    assert set(result.modes.values()) == {"deliberate"}
    assert len(acting(fake)) == before + 3


def test_the_prompt_says_what_the_routine_expects():
    session = lived_in(toy.build_toy())
    fake = quiet_llm()
    sim = Simulation(session, llm_for(session, fake), deliberate_hours=48)
    run(sim.tick(60))
    prompt = acting(fake)[0].user
    assert "(morning)" in prompt or "(afternoon)" in prompt
    assert "Your usual routine now: working at" in prompt


def comparable(events):
    return [e.model_dump(exclude={"branch_id", "trace_id"}) for e in events]


def test_a_routine_world_replays_to_an_identical_log():
    session = lived_in(toy.build_toy())
    start = session.state.seq
    fake = offline_llm(lambda: session.state, seed="routine")
    sim = Simulation(session, llm_for(session, fake), reflect_threshold=1.5)
    run(sim.run(14))
    recorded = session.store.events(session.branch_id, after=start)
    assert any(e.narration.endswith("works at Keller Bakery.") for e in recorded)

    replay = session.fork(start, "replay")
    replay_llm = StructuredLLM(
        ReplayLLM(session.store, session.branch_id), LLMConfig(), Tracer(session.store, LLMConfig())
    )
    run(Simulation(replay, replay_llm, reflect_threshold=1.5).run(14))
    replayed = session.store.events(replay.branch_id, after=start)
    assert comparable(replayed) == comparable(recorded)


def test_a_long_stretch_of_routine_is_paid_for_all_of_it():
    session = lived_in(toy.build_toy(), wage=6)
    sim = Simulation(session, llm_for(session, quiet_llm()), deliberate_hours=48)
    run(sim.tick(60))  # 08:00 -> 09:00, everyone decides afresh
    run(sim.tick(60))  # 09:00 -> 10:00, everyone is at their place of work
    before = session.state.entities[toy.ANNA].inventory[toy.COIN]
    result = run(sim.tick())
    assert result.step_minutes == 7 * 60
    assert session.state.sim_time.hour == 17
    assert session.state.entities[toy.ANNA].inventory[toy.COIN] == before + 6 * 7


def test_nobody_skips_a_day_while_someone_is_still_walking_to_work():
    session = lived_in(toy.build_toy())
    sim = Simulation(session, llm_for(session, quiet_llm()), deliberate_hours=48)
    run(sim.tick(60))
    result = run(sim.tick())
    assert result.step_minutes == 60
