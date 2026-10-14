import asyncio
from datetime import datetime, timedelta

import pytest

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.fixtures import toy
from tinyworld.god import compiler
from tinyworld.god.channel import GodChannel
from tinyworld.god.feasibility import judge, overall, parse_when
from tinyworld.god.parser import GodCommand, resolve, world_index
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.loop import Simulation
from tinyworld.sim.schedule import Scheduler


def run(coroutine):
    return asyncio.run(coroutine)


def llm_for(session, fake):
    return StructuredLLM(fake, LLMConfig(), Tracer(session.store, LLMConfig()))


def channel_with(session, commands=None, **handlers):
    replies = {"god.parse": {"commands": commands or []}, **handlers}
    fake = FakeLLM(replies)
    return GodChannel(llm_for(session, fake), world_digest="A small town."), fake


def offline_channel(session):
    return GodChannel(llm_for(session, offline_llm(lambda: session.state)))


def apply(session, *commands):
    """Apply typed commands without a parser, as the API does after parsing."""
    return run(GodChannel(None).apply(session, "test", [GodCommand(**c) for c in commands]))


def god_events(session, after):
    return session.store.events(session.branch_id, after=after)


# -- resolution and parsing --------------------------------------------------


def test_resolve_by_id_name_and_unique_partial():
    state = toy.build_toy().state
    assert resolve(state, toy.ANNA) == toy.ANNA
    assert resolve(state, "anna keller") == toy.ANNA
    assert resolve(state, "Lena") == toy.LENA
    assert resolve(state, "tavern") is None  # the tavern is "The Golden Stag"
    assert resolve(state, "Golden Stag", "place") == toy.TAVERN
    assert resolve(state, "bakery") is None  # two places match
    assert resolve(state, "nobody") is None and resolve(state, "") is None


def test_parser_prompt_lists_ids_and_quotes_the_god_text():
    session = toy.build_toy()
    channel, fake = channel_with(session, [{"op": "trigger_event", "description": "Bells ring."}])
    run(channel.submit(session, "ring the bells"))
    request = fake.calls[0]
    assert "<god>\nring the bells\n</god>" in request.user
    assert "Anna Keller [person:anna_keller]" in request.user
    assert "Now: 1943-03-14T08:00" in request.user
    assert request.stable_context == "About this world:\nA small town."
    assert "Do not add anything the god did not ask for" in request.system


def test_unknown_target_is_sent_back_to_the_parser_then_becomes_a_question():
    session = toy.build_toy()
    channel, fake = channel_with(session, [{"op": "remove", "target": "person:nobody"}])
    result = run(channel.submit(session, "kill nobody"))
    assert len(fake.calls) == 3
    assert "is not a known id" in fake.calls[1].user
    assert result.verdict == "question" and result.question
    assert session.state.seq == 7


def test_ambiguity_returns_the_parsers_question():
    session = toy.build_toy()
    channel, _ = channel_with(session)
    channel.parser.llm.client.on("god.parse", {"commands": [], "question": "Which bakery room?"})
    result = run(channel.submit(session, "burn the bakery"))
    assert result.verdict == "question" and result.question == "Which bakery room?"


def test_no_model_means_free_text_is_refused_not_guessed():
    session = toy.build_toy()
    result = run(GodChannel(None).submit(session, "kill Otto"))
    assert result.verdict == "reject" and "No model" in result.explanation


# -- operations (ported from v1 test_interventions) --------------------------


def test_spawn_item_place_and_faction():
    session = toy.build_toy()
    result = apply(
        session,
        {"op": "spawn", "kind": "place", "name": "Old Mill", "location": toy.SQUARE},
        {"op": "spawn", "kind": "item", "name": "Printing Press", "location": "Old Mill", "description": "A hand press."},
        {"op": "spawn", "kind": "faction", "name": "Millers Guild", "attrs": {"members": 12}},
    )
    assert result.applied and len(result.event_seqs) == 3
    state = session.state
    assert state.edge("place:old_mill", toy.SQUARE) is not None
    press = state.entities["item:printing_press"]
    assert press.location == "place:old_mill" and press.attrs["description"] == "A hand press."
    assert state.entities["faction:millers_guild"].attrs["members"] == 12


def test_spawn_rejects_duplicates_bad_attrs_and_missing_fields():
    session = toy.build_toy()
    assert "already exists" in apply(session, {"op": "spawn", "kind": "person", "name": "Anna Keller"}).explanation
    bad = apply(session, {"op": "spawn", "kind": "item", "name": "Cart", "attrs": {"wings": 2}})
    assert bad.verdict == "reject" and "not allowed" in bad.explanation and "Allowed:" in bad.explanation
    assert apply(session, {"op": "spawn", "name": "Thing"}).verdict == "reject"
    assert session.state.seq == 7


def test_kill_then_kill_again_is_rejected_with_a_reason():
    session = toy.build_toy()
    first = apply(session, {"op": "remove", "target": "Otto Brandt", "description": "a fever"})
    assert first.applied and not session.state.entities[toy.OTTO].alive
    event = god_events(session, 7)[0]
    assert (event.actor, event.kind, event.location) == ("god", "god", toy.TOWN_HALL)
    assert event.effects[0].cause == "a fever"

    second = apply(session, {"op": "remove", "target": toy.OTTO})
    assert second.verdict == "reject"
    assert second.explanation == "Otto Brandt is already dead."
    assert session.state.seq == 8


def test_erase_removes_the_entity_and_refuses_occupied_places():
    session = toy.build_toy()
    assert apply(session, {"op": "remove", "target": toy.LENA, "attrs": {"mode": "erase"}}).applied
    assert toy.LENA not in session.state.entities
    refused = apply(session, {"op": "remove", "target": toy.BAKERY})
    assert refused.verdict == "reject" and "not empty" in refused.explanation
    assert apply(session, {"op": "remove", "target": toy.BAKERY, "attrs": {"mode": "kill"}}).verdict == "reject"


def test_modify_attribute_and_inventory():
    session = toy.build_toy()
    assert apply(session, {"op": "modify", "target": toy.ANNA, "key": "mood", "value": "furious"}).applied
    assert apply(session, {"op": "modify", "target": toy.ANNA, "item": "coin", "quantity": 100}).applied
    assert apply(session, {"op": "modify", "target": toy.BAKERY, "item": toy.BREAD, "quantity": -5}).applied
    state = session.state
    assert state.entities[toy.ANNA].attrs["mood"] == "furious"
    assert state.entities[toy.ANNA].inventory[toy.COIN] == 112
    assert state.entities[toy.BAKERY].inventory[toy.BREAD] == 15

    for bad in (
        {"op": "modify", "target": toy.ANNA, "key": "wings", "value": 2},
        {"op": "modify", "target": toy.ANNA, "key": "age", "value": "old"},
        {"op": "modify", "target": toy.ANNA, "item": toy.COIN, "quantity": -999},
        {"op": "modify", "target": toy.ANNA, "item": toy.OTTO, "quantity": 1},
        {"op": "modify", "target": toy.ANNA},
        {"op": "modify", "target": "person:ghost", "key": "mood", "value": "x"},
    ):
        assert apply(session, bad).verdict == "reject", bad


def test_move():
    session = toy.build_toy()
    assert apply(session, {"op": "move", "target": toy.LENA, "location": "Market Square"}).applied
    assert session.state.entities[toy.LENA].location == toy.SQUARE
    assert apply(session, {"op": "move", "target": toy.LENA, "location": toy.SQUARE}).verdict == "reject"
    assert apply(session, {"op": "move", "target": toy.LENA, "location": "Atlantis"}).verdict == "reject"
    assert apply(session, {"op": "move", "target": toy.BAKERY, "location": toy.SQUARE}).verdict == "reject"


def test_event_environment_rule_time_and_process():
    session = toy.build_toy()
    result = apply(
        session,
        {"op": "trigger_event", "description": "Church bells ring across the town."},
        {"op": "change_environment", "description": "A drought grips the district."},
        {"op": "change_rule", "key": "ration.bread", "value": 250},
        {"op": "advance_time", "minutes": 120},
        {"op": "start_process", "name": "Dig a new well", "target": toy.OTTO, "location": toy.SQUARE,
         "description": "The council's answer to the drought.", "attrs": {"work_minutes": 1200}},
    )
    assert result.applied and len(result.event_seqs) == 5
    state = session.state
    assert state.fact_holds("fact:a_drought_grips_the_district")
    assert state.rules["ration.bread"] == 250
    assert state.sim_time == toy.START + timedelta(hours=2)
    well = state.processes["process:dig_a_new_well"]
    assert (well.owner, well.location, well.work_minutes) == (toy.OTTO, toy.SQUARE, 1200)

    events = god_events(session, 7)
    assert [e.visibility for e in events] == ["public", "public", "god_only", "god_only", "witnessed"]
    assert all(e.actor == "god" for e in events)

    again = apply(session, {"op": "change_environment", "description": "A drought grips the district."})
    assert again.applied and state is not session.state
    assert session.state.fact_holds("fact:a_drought_grips_the_district_2")

    for bad in (
        {"op": "trigger_event"},
        {"op": "change_rule", "key": "__class__", "value": 1},
        {"op": "advance_time", "minutes": 0},
        {"op": "start_process", "name": "Dig a new well", "target": toy.OTTO},
        {"op": "start_process", "name": "X", "target": "person:ghost"},
        {"op": "trigger_event", "description": "Fire.", "location": "Atlantis"},
    ):
        assert apply(session, bad).verdict == "reject", bad


def test_god_only_visibility_hides_the_event_from_everyone():
    session = toy.build_toy()
    channel = GodChannel(None)
    run(channel.apply(session, "t", [GodCommand(op="trigger_event", description="A quiet omen.", visibility="god_only")]))
    assert channel.last_observations == []
    run(channel.apply(session, "t", [GodCommand(op="trigger_event", description="Thunder.")]))
    assert {o.observer for o in channel.last_observations} == {toy.ANNA, toy.OTTO, toy.LENA}


def test_a_request_is_all_or_nothing():
    session = toy.build_toy()
    result = apply(
        session,
        {"op": "move", "target": toy.LENA, "location": toy.SQUARE},
        {"op": "remove", "target": "person:ghost"},
    )
    assert result.verdict == "reject" and overall(result.judgements) == "reject"
    assert session.state.entities[toy.LENA].location == toy.FARM
    assert session.state.seq == 7


def test_every_god_action_is_an_event_and_state_is_the_fold_of_the_log():
    session = toy.build_toy()
    apply(session, {"op": "spawn", "kind": "person", "name": "Eva Roth", "location": toy.TAVERN, "attrs": {"age": 40}})
    apply(session, {"op": "modify", "target": "Eva Roth", "key": "mood", "value": "wary"})
    apply(session, {"op": "change_rule", "key": "curfew", "value": True})
    apply(session, {"op": "remove", "target": toy.OTTO})
    apply(session, {"op": "advance_time", "minutes": 30})
    assert len(god_events(session, 7)) == 5
    assert session.store.state_at(session.branch_id, use_snapshots=False) == session.state


# -- time: scheduling and forks ----------------------------------------------


def test_parse_when():
    assert parse_when("") is None
    assert parse_when("1943-06-01") == datetime(1943, 6, 1, 8)
    assert parse_when("1943-06-01T14:30") == datetime(1943, 6, 1, 14, 30)
    assert judge(toy.build_toy().state, GodCommand(op="trigger_event", description="x", when="next summer")).verdict == "reject"


def test_future_command_is_scheduled_and_fires_when_due():
    session = toy.build_toy()
    result = apply(session, {"op": "change_environment", "description": "A drought begins.", "when": "1943-03-14T11:00"})
    assert result.applied and result.event_seqs == [] and len(result.scheduled) == 1
    assert "Scheduled for 14 March 1943, 11:00" in result.explanation
    assert not session.state.fact_holds("fact:a_drought_begins")

    sim = Simulation(session, None)
    run(sim.run(2))
    assert not session.state.fact_holds("fact:a_drought_begins")
    fired = run(sim.tick())
    assert session.state.fact_holds("fact:a_drought_begins")
    assert [e.narration for e in fired.events if e.actor == "god"] == ["A drought begins."]
    assert Scheduler(session.store).pending(session.branch_id) == []
    run(sim.tick())
    assert len([e for e in god_events(session, 7) if e.actor == "god"]) == 1


def test_scheduled_events_follow_the_branch_they_were_made_on():
    session = toy.build_toy()
    before = session.state.seq
    apply(session, {"op": "trigger_event", "description": "The dam breaks.", "when": "1943-03-14T10:00"})
    session.commit([EventDraft(actor="system", effects=[fx.AdvanceTime(minutes=1)], visibility="god_only")])
    scheduler = Scheduler(session.store)
    assert len(scheduler.pending(session.branch_id)) == 1

    earlier = session.fork(before - 1, "before-the-command")
    assert scheduler.pending(earlier.branch_id) == []
    later = session.fork(session.state.seq, "after-the-command")
    assert len(scheduler.pending(later.branch_id)) == 1

    run(Simulation(later, None).run(3))
    assert scheduler.pending(later.branch_id) == []
    assert len(scheduler.pending(session.branch_id)) == 1


def test_retroactive_command_needs_a_fork_and_leaves_the_present_alone():
    session = toy.build_toy()
    sim = Simulation(session, None)
    run(sim.run(5))
    head = session.state.seq

    result = apply(session, {"op": "remove", "target": toy.OTTO, "when": "1943-03-14T10:00"})
    assert result.verdict == "needs_fork" and "branch the timeline" in result.explanation
    assert session.state.seq == head and session.state.entities[toy.OTTO].alive
    assert session.store.event(session.branch_id, result.fork_seq).sim_time <= datetime(1943, 3, 14, 10)
    assert session.store.event(session.branch_id, result.fork_seq + 1).sim_time > datetime(1943, 3, 14, 10)

    fork, applied = run(GodChannel(None).apply_in_fork(session, result, "otto-dies"))
    assert applied.applied and applied.branch_id == fork.branch_id
    assert not fork.state.entities[toy.OTTO].alive
    assert fork.state.sim_time == datetime(1943, 3, 14, 10)
    assert session.state.entities[toy.OTTO].alive and session.state.seq == head
    with pytest.raises(ValueError):
        run(GodChannel(None).apply_in_fork(session, applied))


# -- exit criterion ----------------------------------------------------------

EINSTEIN_PROFILE = {
    "age": 0,
    "occupation": "",
    "persona": {
        "summary": "A newborn boy with an unusually quick, pattern-seeking mind.",
        "aptitudes": {"mathematics": 10, "physics": 10, "music": 7},
        "knowledge": {"knows": [], "does_not_know": ["everything; he is a newborn"]},
    },
    "explanation": "This is a new child born in 1943 who shares the name and gifts of the "
    "historical physicist. He has none of that man's life or discoveries.",
}


def test_einstein_is_born_in_a_house_in_this_town():
    session = toy.build_toy()
    channel, fake = channel_with(
        session,
        [
            {
                "op": "spawn", "kind": "person", "name": "Albert Einstein",
                "location": "a house in this town",
                "description": "born today as a child; a gift for physics",
            }
        ],
        **{"agent.persona": EINSTEIN_PROFILE},
    )
    result = run(channel.submit(session, "Einstein is born in a house in this town"))

    assert result.verdict == "apply_adjusted"
    assert "a home was created: Einstein House" in result.explanation
    assert "has none of that man's life or discoveries" in result.explanation

    state = session.state
    child = state.entities["person:albert_einstein"]
    house = state.entities["place:einstein_house"]
    assert child.location == house.id and child.attrs["home"] == house.id
    assert state.path(house.id, toy.SQUARE) is not None
    assert child.attrs["age"] == 0 and child.attrs["birth_date"] == "1943-03-14"
    assert child.attrs["tier"] == 2
    persona = persona_of(child)
    assert persona.aptitudes["physics"] == 10 and persona.knowledge.knows == []

    persona_prompt = fake.calls_for("agent.persona")[0]
    assert "real historical person" in persona_prompt.system
    assert "A newborn or small child knows nothing yet" in persona_prompt.system

    event = god_events(session, 7)[0]
    assert event.narration == "A child, Albert Einstein, is born."
    assert [type(e).__name__ for e in event.effects] == ["CreateEntity", "SetEdge", "CreateEntity"]
    # Too young to decide for himself: the loop does not ask him to act.
    sim = Simulation(session, llm_for(session, offline_llm(lambda: session.state)))
    assert "person:albert_einstein" not in {e.id for e in sim.active_agents(session.state, 0)}


def test_adult_spawned_without_a_model_gets_a_default_persona_and_acts():
    session = toy.build_toy()
    result = apply(
        session,
        {"op": "spawn", "kind": "person", "name": "Eva Roth", "location": toy.TAVERN,
         "description": "A travelling seamstress.", "attrs": {"age": 41}},
    )
    assert result.verdict == "apply"
    eva = session.state.entities["person:eva_roth"]
    assert eva.attrs["tier"] == 0 and eva.attrs["birth_date"].startswith("1902")
    assert persona_of(eva).summary == "A travelling seamstress."
    assert compiler.default_profile(session.state, GodCommand(op="spawn", name="X")).age == 30


def test_anachronism_is_flagged_but_the_gods_will_is_done():
    session = toy.build_toy()
    apply(session, {"op": "change_rule", "key": "tech.not_yet", "value": ["television", "atomic bomb"]})
    result = apply(session, {"op": "spawn", "kind": "item", "name": "Television Set", "location": toy.TAVERN})
    assert result.applied and "does not exist yet in this world" in result.explanation
    assert "item:television_set" in session.state.entities
    project = apply(session, {"op": "start_process", "name": "Build an atomic bomb", "target": toy.OTTO})
    assert project.applied and "whether it can succeed is up to the world" in project.explanation


# -- offline parser ----------------------------------------------------------


@pytest.mark.parametrize(
    "text, check",
    [
        ("kill Otto Brandt", lambda s: not s.entities[toy.OTTO].alive),
        ("move Lena Vogel to Market Square", lambda s: s.entities[toy.LENA].location == toy.SQUARE),
        ("spawn item Brass Bell at Town Hall", lambda s: s.entities["item:brass_bell"].location == toy.TOWN_HALL),
        ("Clara Keller is born at Keller Bakery", lambda s: s.entities["person:clara_keller"].attrs["age"] == 0),
        ("skip 3h", lambda s: s.sim_time == toy.START + timedelta(hours=3)),
        ("set rule curfew = dusk", lambda s: s.rules["curfew"] == "dusk"),
        ("A storm tears the roof off the tavern", lambda s: s.seq == 8),
    ],
)
def test_offline_god_commands(text, check):
    session = toy.build_toy()
    result = run(offline_channel(session).submit(session, text))
    assert result.applied, result.explanation
    assert check(session.state)


def test_world_index_marks_the_dead():
    session = toy.build_toy()
    apply(session, {"op": "remove", "target": toy.OTTO})
    assert "Otto Brandt [person:otto_brandt] (dead)" in world_index(session.state)
