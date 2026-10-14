import asyncio
import re
from datetime import timedelta

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.reducers import EffectError, apply_effect
from tinyworld.core.state import Commitment
from tinyworld.fixtures import toy
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.agents import routine as daily
from tinyworld.sim import commitments as pledges
from tinyworld.sim.loop import Simulation
from tinyworld.sim.scene import SceneTurn, openings


def run(coroutine):
    return asyncio.run(coroutine)


def llm_for(session, fake):
    return StructuredLLM(fake, LLMConfig(), Tracer(session.store, LLMConfig()))


def commit(session, *effects):
    session.commit([EventDraft(actor="system", effects=list(effects), visibility="god_only")])


def together(session):
    """Anna and Otto in the bakery, Lena on the farm."""
    commit(session, fx.MoveEntity(entity=toy.OTTO, to=toy.BAKERY))
    return session


def importance(request):
    return {"scores": [3] * len(re.findall(r"^\d+\. ", request.user, re.MULTILINE))}


def world(session, acts, scene):
    return FakeLLM(
        {
            "agent.act": lambda r: acts.get(r.context.agent, {"verb": "wait", "text": "wait"}),
            "agent.scene": scene,
            "memory.importance": importance,
            "agent.reflect": {"insights": [], "beliefs": []},
            "memory.summarize": {"text": "Earlier.", "importance": 2},
        }
    )


GREETING = {
    "verb": "speak", "text": "ask about the grain",
    "say": {"text": "Otto, where is the grain going?", "to": [toy.OTTO]},
}


def commitment(session, **changes):
    state = session.state
    fields = dict(
        id="commitment:c1", by=toy.OTTO, to=toy.ANNA, kind="meet",
        text="be at the tavern", due=state.sim_time + timedelta(hours=2),
        made_at=state.sim_time, made_seq=state.seq, place=toy.TAVERN,
    )
    fields.update(changes)
    return Commitment(**fields)


# -- the vocabulary ----------------------------------------------------------


def test_a_commitment_must_be_between_two_people_and_fall_due_later():
    session = toy.build_toy()
    state = session.state.model_copy(deep=True)
    apply_effect(state, fx.MakeCommitment(commitment=commitment(session)))
    assert [c.id for c in state.open_commitments(toy.ANNA)] == ["commitment:c1"]

    fresh = session.state.model_copy(deep=True)
    for bad in (
        commitment(session, by=toy.ANNA, to=toy.ANNA),
        commitment(session, place=toy.COIN),
        commitment(session, due=session.state.sim_time),
        commitment(session, to="place:bakery"),
    ):
        with pytest.raises(EffectError):
            apply_effect(fresh, fx.MakeCommitment(commitment=bad))


def test_a_commitment_can_only_be_resolved_once():
    session = toy.build_toy()
    state = session.state.model_copy(deep=True)
    apply_effect(state, fx.MakeCommitment(commitment=commitment(session)))
    apply_effect(state, fx.ResolveCommitment(commitment_id="commitment:c1", status="kept"))
    with pytest.raises(EffectError):
        apply_effect(state, fx.ResolveCommitment(commitment_id="commitment:c1", status="broken"))


def test_commitments_replay_with_the_log():
    session = toy.build_toy()
    commit(session, fx.MakeCommitment(commitment=commitment(session)))
    assert session.store.state_at(session.branch_id, use_snapshots=False) == session.state


# -- scenes ------------------------------------------------------------------


def test_a_line_to_someone_here_is_answered_in_the_same_tick():
    session = together(toy.build_toy())
    fake = world(
        session, {toy.ANNA: GREETING},
        [
            {"say": "Ask the district office, not me.", "tone": "cold"},
            {"say": "I will.", "tone": "neutral", "end": True},
        ],
    )
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(60))

    lines = [e.narration for e in result.events if e.kind == "utterance"]
    assert len(lines) == 3
    assert lines[0].startswith('Anna Keller says to Otto Brandt: "Otto, where')
    assert lines[1].startswith('Otto Brandt says to Anna Keller: "Ask the district')
    assert result.scenes == 1 and result.scene_turns == 2


def test_tone_changes_how_the_other_person_regards_the_speaker():
    session = together(toy.build_toy())
    before = session.state.relation(toy.ANNA, toy.OTTO).value
    fake = world(session, {toy.ANNA: GREETING}, {"say": "Hold your tongue.", "tone": "angry", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    run(sim.tick(60))
    assert session.state.relation(toy.ANNA, toy.OTTO).value == before - 3


def test_a_promise_in_a_scene_becomes_a_commitment_with_a_due_time():
    session = together(toy.build_toy())
    promise = {
        "say": "I will be at the tavern by evening.", "tone": "warm", "move": "promise",
        "promise": {"kind": "meet", "text": "be at the tavern", "place": "tavern", "hours": 3},
        "end": True,
    }
    fake = world(session, {toy.ANNA: GREETING}, promise)
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(60))

    assert result.commitments_made == 1
    made = session.state.open_commitments()[0]
    assert (made.by, made.to, made.place) == (toy.OTTO, toy.ANNA, toy.TAVERN)
    assert made.due == session.state.sim_time + timedelta(hours=3)
    heard = [m.text for m in sim.memory.list(session.branch_id, toy.ANNA)]
    assert any("promised" in text and "tavern" in text for text in heard)


def test_a_promise_to_meet_nowhere_real_is_dropped():
    session = together(toy.build_toy())
    promise = {
        "say": "Meet me on the moon.", "move": "promise", "end": True,
        "promise": {"kind": "meet", "text": "be on the moon", "place": "the moon", "hours": 3},
    }
    fake = world(session, {toy.ANNA: GREETING}, promise)
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(60))
    assert result.commitments_made == 0 and session.state.open_commitments() == []


def test_a_scene_stops_at_the_turn_limit():
    session = together(toy.build_toy())
    fake = world(session, {toy.ANNA: GREETING}, {"say": "And another thing.", "tone": "neutral"})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    sim.scenes.max_turns = 3
    result = run(sim.tick(60))
    assert result.scene_turns == 3


def test_nobody_answers_when_the_listener_is_somewhere_else():
    session = toy.build_toy()  # Otto is at the town hall
    fake = world(session, {toy.ANNA: GREETING}, {"say": "Hm.", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(60))
    assert result.scenes == 0


def test_openings_ignore_people_who_already_spoke_this_tick():
    session = together(toy.build_toy())
    both = {
        toy.ANNA: GREETING,
        toy.OTTO: {
            "verb": "speak", "text": "answer",
            "say": {"text": "Anna, a word.", "to": [toy.ANNA]},
        },
    }
    fake = world(session, both, {"say": "Hm.", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(60))
    assert result.scenes == 0


def test_a_scene_turn_that_fails_to_parse_ends_the_scene():
    session = together(toy.build_toy())
    fake = world(session, {toy.ANNA: GREETING}, "not json at all")
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(60))
    assert result.scenes == 1 and result.scene_turns == 1
    assert [e for e in result.events if e.kind == "utterance"]


# -- promises falling due ----------------------------------------------------


def test_a_kept_promise_raises_trust_and_is_remembered_by_both():
    session = together(toy.build_toy())
    commit(session, fx.MakeCommitment(commitment=commitment(session)), fx.MoveEntity(entity=toy.OTTO, to=toy.TAVERN))
    before = session.state.relation(toy.ANNA, toy.OTTO).value
    fake = world(session, {}, {"say": "", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    run(sim.tick(180))

    assert session.state.commitments["commitment:c1"].status == "kept"
    assert session.state.relation(toy.ANNA, toy.OTTO).value == before + pledges.KEPT_TRUST
    assert any("kept" in m.text for m in sim.memory.list(session.branch_id, toy.ANNA))
    assert any("kept my promise" in m.text for m in sim.memory.list(session.branch_id, toy.OTTO))


def test_a_broken_promise_costs_trust():
    session = together(toy.build_toy())
    commit(session, fx.MakeCommitment(commitment=commitment(session)))
    before = session.state.relation(toy.ANNA, toy.OTTO).value
    fake = world(session, {}, {"say": "", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    result = run(sim.tick(180))

    assert session.state.commitments["commitment:c1"].status == "broken"
    assert session.state.relation(toy.ANNA, toy.OTTO).value == before + pledges.BROKEN_TRUST
    assert result.commitments_resolved == 1


def test_a_promise_to_give_is_kept_by_giving():
    session = together(toy.build_toy())
    pledge = commitment(session, kind="give", place=None, item=toy.COIN, quantity=5, text="repay five marks")
    commit(session, fx.MakeCommitment(commitment=pledge))
    commit(session, fx.TransferItem(item=toy.COIN, quantity=5, source=toy.OTTO, dest=toy.ANNA))
    fake = world(session, {}, {"say": "", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    run(sim.tick(180))
    assert session.state.commitments["commitment:c1"].status == "kept"


def test_a_promise_to_someone_now_dead_lapses():
    session = together(toy.build_toy())
    commit(session, fx.MakeCommitment(commitment=commitment(session)), fx.Kill(entity=toy.ANNA, cause="test"))
    fake = world(session, {}, {"say": "", "end": True})
    sim = Simulation(session, llm_for(session, fake), routines=False)
    run(sim.tick(180))
    assert session.state.commitments["commitment:c1"].status == "released"


def test_a_promise_to_be_somewhere_is_carried_out_by_routine_in_time():
    from tinyworld.agents import routine as daily

    session = together(toy.build_toy())
    commit(
        session,
        fx.SetAttr(entity=toy.OTTO, key="home", value=toy.TAVERN),
        fx.SetAttr(entity=toy.OTTO, key="workplace", value=toy.TOWN_HALL),
        fx.MakeCommitment(
            commitment=commitment(session, due=session.state.sim_time + timedelta(hours=1))
        ),
    )
    otto = session.state.entities[toy.OTTO]
    # An hour ahead, the promise does not yet change the day.
    assert daily.current_block(session.state, otto).kind != "promise"
    lead = daily.promise_lead(session.state, otto, session.state.open_commitments()[0])
    assert lead is not None and lead > 15
    soon = session.state.sim_time + timedelta(hours=1) - timedelta(minutes=lead)
    block = daily.current_block(session.state, otto, soon)
    assert block.kind == "promise" and block.place == toy.TAVERN
    assert block.until == session.state.open_commitments()[0].due
    intent = daily.routine_intent(session.state, otto, block)
    assert intent.verb.value == "move" and intent.target == toy.TAVERN


def test_a_promise_to_give_has_no_place_to_set_out_for():
    from tinyworld.agents import routine as daily

    session = together(toy.build_toy())
    otto = session.state.entities[toy.OTTO]
    gift = commitment(session, kind="give", place=None, item=toy.COIN)
    assert daily.promise_lead(session.state, otto, gift) is None


def test_the_prompt_lists_promises_both_ways():
    session = together(toy.build_toy())
    commit(session, fx.MakeCommitment(commitment=commitment(session)))
    lines = pledges.lines_for(session.state, toy.ANNA)
    assert lines and "Otto Brandt promised you" in lines[0]
    assert "You promised Anna Keller" in pledges.lines_for(session.state, toy.OTTO)[0]


def test_scene_turn_schema_defaults_are_a_quiet_end():
    turn = SceneTurn()
    assert turn.say == "" and turn.move == "none" and not turn.end


def test_a_step_is_cut_short_so_nobody_misses_the_time_to_set_out():
    session = together(toy.build_toy())
    commit(
        session,
        fx.MakeCommitment(
            commitment=commitment(session, due=session.state.sim_time + timedelta(hours=2))
        ),
    )
    sim = Simulation(session, None)
    lead = daily.promise_lead(
        session.state, session.state.entities[toy.OTTO], session.state.open_commitments()[0]
    )
    assert sim._before_promises(600) == 120 - lead
    assert sim._before_promises(10) == 10


def test_ordinary_routine_is_not_worth_a_model_call_but_speech_and_news_are():
    from tinyworld.gm.perception import Observation
    from tinyworld.sim.loop import mundane

    def seen(text, **fields):
        return Observation(
            observer=toy.ANNA, event_seq=1, sim_time=session_time(), mode="visual",
            confidence=1.0, text=text, **fields,
        )

    def session_time():
        return toy.START

    assert mundane(seen("Otto Brandt sleeps."))
    assert mundane(seen("Lena Vogel works at Keller Bakery."))
    assert mundane(seen("Otto Brandt goes from Town Hall to Market Square."))
    assert not mundane(seen("Otto Brandt sleeps.", addressed=True))
    assert not mundane(seen('Otto says: "the grain is gone".', speaker=toy.OTTO))
    assert not mundane(seen("Otto Brandt attacks Lena Vogel."))
