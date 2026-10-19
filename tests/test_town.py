import asyncio
from datetime import date, timedelta

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy, Fixed
from tinyworld.core.events import EventDraft
from tinyworld.fixtures import toy
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim import newspaper
from tinyworld.sim.loop import Simulation
from tinyworld.sim.replay import replay
from tinyworld.sim.town import Town
from tinyworld.world import chance, petitions


def run(coroutine):
    return asyncio.run(coroutine)


def make(entropy=None, **town):
    session = toy.build_toy()
    config = LLMConfig()
    llm = StructuredLLM(offline_llm(lambda: session.state, seed="t"), config, Tracer(session.store, config))
    sim = Simulation(session, llm)
    entropy = entropy or Entropy(session.store, session.branch_id, seq=lambda: session.state.seq)
    return Town(sim, entropy, **town), session


# -- petitions ---------------------------------------------------------------


def test_a_resident_can_petition_through_the_rules():
    town, session = make(petitioning=False)
    from tinyworld.core.events import Intent, Verb

    run(town.apply([Intent(agent=toy.ANNA, verb=Verb.PETITION, text="Keep the requisitioners away.",
                           args={"kind": "prayer"})], 0))
    open_ = petitions.open_petitions(session.state)
    assert [p.by for p in open_] == [toy.ANNA] and open_[0].kind == "prayer"


def test_a_petition_needs_words_a_known_kind_and_no_other_open_one():
    town, session = make(petitioning=False)
    state = session.state
    anna = state.entities[toy.ANNA]
    assert isinstance(petitions.file(state, anna, {}, ""), str)
    assert isinstance(petitions.file(state, anna, {"kind": "curse"}, "x"), str)
    effects, _ = petitions.file(state, anna, {"kind": "plea"}, "Help.")
    session.commit([EventDraft(actor="system", effects=effects, visibility="god_only")])
    assert "already" in petitions.file(session.state, session.state.entities[toy.ANNA], {}, "More.")


def _filed(town, session, who=toy.ANNA, text="Feed my children."):
    state = session.state
    effects, _ = petitions.file(state, state.entities[who], {"kind": "request"}, text)
    session.commit([EventDraft(actor="system", effects=effects, visibility="god_only")])
    return petitions.open_petitions(session.state)[0]


def test_each_answer_closes_the_petition_and_moves_faith():
    expected = {"grant": 60, "whisper": 56, "sign": 53, "refuse": 45, "punish": 38, "ignore": 42}
    for power, faith in expected.items():
        town, session = make(petitioning=False)
        p = _filed(town, session)
        effects = [fx.ChangeQuantity(holder=toy.ANNA, item=toy.BREAD, delta=1)] if power == "grant" else None
        run(town.answer(p.id, power, "so be it", effects))
        state = session.state
        assert petitions.open_petitions(state) == []
        assert petitions.get(state, p.id).status == ("silence" if power == "ignore" else "answered")
        assert state.entities[toy.ANNA].attrs["faith"] == faith, power


def test_an_answer_is_remembered_by_the_petitioner_and_those_who_saw():
    town, session = make(petitioning=False)
    p = _filed(town, session)
    run(town.answer(p.id, "refuse", "No."))
    mine = town.sim.memory.list(session.branch_id, toy.ANNA)
    assert any("refused me" in m.text for m in mine)


def test_silence_after_the_timeout_is_an_answer_and_is_remembered():
    town, session = make(petitioning=False, god=None)
    p = _filed(town, session)
    session.commit([EventDraft(actor="system", visibility="god_only",
                               effects=[fx.AdvanceTime(minutes=60 * 13)])])
    run(town._answers())
    assert petitions.get(session.state, p.id).status == "silence"
    assert session.state.entities[toy.ANNA].attrs["faith"] == 42
    assert any("no answer" in m.text for m in town.sim.memory.list(session.branch_id, toy.ANNA))


def test_a_petition_cannot_be_answered_twice():
    town, session = make(petitioning=False)
    p = _filed(town, session)
    run(town.answer(p.id, "whisper", "Wait."))
    try:
        petitions.answer(session.state, p.id, "grant")
    except ValueError as exc:
        assert "no open petition" in str(exc)
    else:
        raise AssertionError("answered twice")


def test_petitions_are_specific_to_the_person():
    _, session = make()
    anna = session.state.entities[toy.ANNA]
    texts = {petitions.compose(anna, Fixed([i / 10] * 3))[0] for i in range(10)}
    assert any("requisition" in t or "supplied" in t or "children" in t for t in texts)


def test_residents_petition_on_their_own_and_not_twice_in_a_day():
    town, session = make(entropy=Fixed([0.0] * 400))
    for _ in range(6):
        run(town.advance(60))
    filed = petitions.all_petitions(session.state)
    assert filed, "nobody petitioned at maximum urgency"
    by = {}
    for p in filed:
        by.setdefault(p.by, []).append(p.filed)
    for times in by.values():
        for a, b in zip(times, times[1:]):
            assert b - a >= petitions.COOLDOWN


# -- chaos -------------------------------------------------------------------


def test_chaos_zero_means_no_chance_events():
    _, session = make()
    state = session.state
    assert all(chance.roll(state, 1440, Fixed([0.0] * 20)) is None for _ in range(5))


def test_chaos_scales_how_often_and_how_hard():
    _, session = make()
    state = session.state.model_copy(deep=True)
    hits = {}
    for level in (0.2, 1.0):
        state.rules["chaos"] = level
        e = Entropy()
        hits[level] = sum(chance.roll(state, 1440, e) is not None for _ in range(400))
    assert hits[1.0] > hits[0.2] * 2


def test_every_chance_event_applies_cleanly():
    from tinyworld.core.reducers import apply_effect

    _, session = make()
    state = session.state.model_copy(deep=True)
    state.rules["chaos"] = 1.0
    e = Entropy()
    kinds = set()
    for _ in range(600):
        f = chance.roll(state, 1440, e)
        if f is None:
            continue
        kinds.add(f.kind)
        working = state.model_copy(deep=True)
        for effect in f.draft.effects:
            apply_effect(working, effect)
    assert {"fever", "theft", "fire", "windfall", "accident", "quarrel", "rumour"} <= kinds


# -- the paper ---------------------------------------------------------------


def test_a_day_becomes_a_paper_whose_stories_cite_real_events():
    town, session = make(chaos=0.0, petitioning=False)
    run(town.run(30, 60))
    editions = town.editions
    assert editions, "no edition was printed"
    events = session.store.events(session.branch_id)
    for edition in editions.values():
        assert newspaper.check(edition, events) == []
        assert edition.headline


def test_the_paper_is_an_item_residents_can_find_and_is_stored():
    town, session = make(chaos=0.0, petitioning=False)
    run(town.run(30, 60))
    day = sorted(town.editions)[0]
    assert newspaper.item_id(day) in session.state.entities
    assert newspaper.load(session.store, session.world_id, day).headline == town.editions[day].headline


def test_a_quiet_day_is_reported_as_quiet():
    e = newspaper.write([], date(2000, 1, 1))
    assert e.headline == "A quiet day"


def test_the_paper_checks_catch_a_made_up_event():
    e = newspaper.Edition(day="1943-03-14", headline="h", stories=[newspaper.Story(headline="x", events=[9999])])
    assert newspaper.check(e, []) != []


# -- recording ---------------------------------------------------------------


def test_a_town_run_replays_exactly():
    town, session = make(entropy=Entropy(), chaos=1.0)
    run(town.run(30, 60))
    assert petitions.all_petitions(session.state) or chance.level(session.state) > 0
    report = run(replay(session.store, session.branch_id, LLMConfig()))
    assert report.identical, report.first_difference
    assert report.replayed_events == report.recorded_events > 30


def test_residents_read_the_paper_and_believe_it():
    town, session = make(chaos=0.0, petitioning=False)
    run(town.run(30, 60))
    people = session.state.people()
    heard = [m for p in people for m in town.sim.memory.list(session.branch_id, p.id) if "I read the paper" in m.text]
    assert heard
    assert any(
        b.subject == "town" and b.predicate == "news"
        for p in people for b in town.sim.beliefs.current(session.branch_id, p.id)
    )


def test_a_model_narrator_is_used_and_a_made_up_event_sends_it_back_to_the_script():
    from tinyworld.llm.fake import FakeLLM
    from tinyworld.sim import newspaper as np_

    town, session = make(chaos=0.0, petitioning=False)
    run(town.run(26, 60))
    events = session.store.events(session.branch_id)
    day = sorted(town.editions)[0]
    from datetime import date as d

    todays = np_.day_events(events, d.fromisoformat(day))
    cited = todays[0].seq
    cfg = LLMConfig()
    good = StructuredLLM(FakeLLM({"narrator.paper": {"day": day, "headline": "A day in town", "stories": [
        {"headline": "Something happened", "body": "x", "events": [cited]}], "rumours": []}}), cfg, Tracer(session.store, cfg))
    from tinyworld.llm.types import CallContext

    e = run(np_.write_with_model(good, events, d.fromisoformat(day), session.state, CallContext(session.branch_id, 0)))
    assert e.headline == "A day in town" and np_.check(e, events) == []
    bad = StructuredLLM(FakeLLM({"narrator.paper": {"day": day, "headline": "Invented", "stories": [
        {"headline": "Made up", "body": "x", "events": [999999]}], "rumours": []}}), cfg, Tracer(session.store, cfg))
    e2 = run(np_.write_with_model(bad, events, d.fromisoformat(day), session.state, CallContext(session.branch_id, 1)))
    assert e2.headline != "Invented" and np_.check(e2, events) == []


def test_far_off_senses_are_unreliable_and_a_replay_hears_the_same_slips():
    from tinyworld.gm.perception import Observation, distort
    from tinyworld.core.entropy import Fixed
    from datetime import datetime

    o = Observation(observer=toy.ANNA, event_seq=1, sim_time=datetime(2000, 1, 1), mode="auditory", confidence=0.5,
                    text="Otto says he will take the grain on Friday", actor=toy.OTTO)
    slipped = distort(o, Fixed([0.0, 0.0, 0.0]))
    assert slipped.text != o.text and slipped.confidence < o.confidence
    assert distort(o, Fixed([0.99])).text == o.text  # no slip this time
    near = o.model_copy(update={"confidence": 1.0})
    assert distort(near, Fixed([0.0])).text == near.text  # close and certain: exact

    town, session = make(chaos=0.0, petitioning=False, noise=True)
    run(town.run(14, 60))
    draws = [r for r in session.store.journal(session.branch_id) if r["op"] == "draw" and '"noise.' in r["args_json"]]
    report = run(replay(session.store, session.branch_id, LLMConfig()))
    assert report.identical, report.first_difference
    if draws:
        mem_live = sorted(m.text for p in session.state.people() for m in town.sim.memory.list(session.branch_id, p.id))
        assert mem_live
