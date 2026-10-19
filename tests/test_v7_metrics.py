import asyncio

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.eval import multiverse, v7_metrics as m
from tinyworld.eval.v7_experiments import berlin_session, town_for
from tinyworld.fixtures import berlin
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.town import Town
from tinyworld.world import petitions

ANNA, OTTO = "person:anna_keller", "person:otto_brandt"


def run(c):
    return asyncio.run(c)


def lived():
    s = berlin_session()
    base = town_for(s, chaos=0.5)
    town = Town(base.sim, base.entropy, chaos=0.5)
    run(town.run(30, 60))
    return s, town


def speak(s, a, b, text, kind="tell"):
    s.commit([EventDraft(actor=a, kind="utterance", location=s.state.entities[a].location, narration=text,
                         effects=[fx.Utter(speaker=a, text=text, addressees=[b], message_type=kind)])])


def test_liveliness_counts_what_is_more_than_routine():
    s, town = lived()
    r = m.liveliness(s)
    assert r["events"] > 0 and r["per_resident_day"] > 0 and r["residents"] == 10


def test_disagreement_is_the_share_of_conversations_with_a_refusal_or_threat():
    s = berlin_session()
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.MoveEntity(entity=OTTO, to=s.state.entities[ANNA].location)])])
    speak(s, ANNA, OTTO, "Good morning, Otto.")
    speak(s, OTTO, ANNA, "Good morning.")
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=300)])])
    speak(s, ANNA, OTTO, "I will not hand over the flour.")
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=300)])])
    speak(s, OTTO, ANNA, "You will regret this.", "threaten")
    r = m.disagreement(s)
    assert r["conversations"] == 3 and r["with_disagreement"] == 2 and r["share"] == pytest.approx(0.667, abs=0.01)


def test_coherence_counts_violations_and_anachronisms():
    s, town = lived()
    c = m.coherence(s)
    assert c == {"invariant_violations": 0, "anachronisms": 0}
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.SetRule(key="tech.not_yet", value=["television"])])])
    speak(s, ANNA, OTTO, "Have you seen the television?")
    assert m.coherence(s)["anachronisms"] == 1


def test_readability_reports_coverage_and_invented_events():
    s, town = lived()
    r = m.readability(s, town.editions)
    assert r["editions"] >= 1 and r["invented_events"] == 0
    assert r["coverage_of_weightiest_events"] is None or 0 <= r["coverage_of_weightiest_events"] <= 1


def test_cost_is_per_resident_per_day():
    s, town = lived()
    c = m.cost(s)
    assert c["calls"] > 0 and c["calls_per_resident_day"] > 0


def test_a_judge_from_the_residents_own_family_is_refused():
    llm = StructuredLLM(FakeLLM({"eval.petition": {"specific": True, "consequential": True}}), LLMConfig(), None)
    with pytest.raises(ValueError, match="same family"):
        m.Judge(llm, "claude-opus-5-5", ["claude-sonnet-5-5"])
    assert m.Judge(llm, "gemini-3.5-flash", ["qwen2.5:7b-instruct", "claude-sonnet-5-5"])
    assert m.family("google/gemini-3.6-flash") == "gemini" == m.family("gemini-2.5-flash")


def test_a_judge_is_trusted_only_after_it_agrees_with_people():
    llm = StructuredLLM(FakeLLM({}), LLMConfig(), None)
    j = m.Judge(llm, "gemini-3.5-flash", ["qwen2.5:7b"])
    human = [True, False] * 15
    bad = m.calibrate([True] * 30, human)
    assert not bad["trusted"] and bad["kappa"] == 0
    few = m.calibrate(human[:10], human[:10])
    assert not few["trusted"], "too few labels to trust"
    good = j.calibrate(human, human)
    assert good["trusted"] and j.trusted and j.agreement == 1.0
    almost = m.calibrate([not x if i < 3 else x for i, x in enumerate(human)], human)
    assert almost["trusted"] and almost["agreement"] == 0.9


def test_the_petition_judge_scores_through_a_model_and_a_rule_judge_needs_none():
    s, town = lived()
    ps = petitions.all_petitions(s.state)
    assert ps, "no petitions in 30 hours"
    r = run(m.petition_quality(s))
    assert r["petitions"] == len(ps) and r["judge"] == "rules" and 0 <= r["specific"] <= 1
    cfg = LLMConfig()
    llm = StructuredLLM(FakeLLM({"eval.petition": {"specific": True, "consequential": False}}), cfg, Tracer(s.store, cfg))
    judge = m.Judge(llm, "gemini-3.5-flash", ["claude-sonnet-5-5"])
    r2 = run(m.petition_quality(s, judge))
    assert r2["specific"] == 1.0 and r2["consequential"] == 0.0 and r2["judge_trusted"] is False


def test_a_full_report_hangs_together():
    s, town = lived()
    rep = run(m.report(s, editions=town.editions))
    assert set(rep) >= {"liveliness", "disagreement", "coherence", "cost", "petitions", "readability"}
