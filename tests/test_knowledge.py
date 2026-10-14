import asyncio

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft, Intent, Verb
from tinyworld.core.reducers import EffectError, apply_effect
from tinyworld.eval.invariants import check_log
from tinyworld.fixtures import toy
from tinyworld.gm import rules
from tinyworld.sim.loop import Simulation
from tinyworld.world import knowledge, projects
from test_routine import llm_for, quiet_llm, run
from test_scene import together


def graph():
    built = knowledge.build(
        ["Radio repair", "Electrical wiring", "Mathematics"],
        ["Radio transmitter", "Rocket motor"],
        {"Radio transmitter": ["Radio repair", "Electrical wiring"],
         "Rocket motor": ["Mathematics", "Radio transmitter"]},
    )
    # Trades only some people have, as opposed to what everyone knows.
    for key in ("idea:radio_repair", "idea:electrical_wiring", "idea:mathematics"):
        built[key] = built[key].model_copy(update={"status": "rare"})
    return built


def with_graph(session):
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[
                    fx.SetRule(key=knowledge.KEY, value=knowledge.graph_value(graph())),
                    fx.SetAttr(entity=toy.ANNA, key="knowledge",
                               value={"idea:radio_repair": 2, "idea:electrical_wiring": 2}),
                ],
            )
        ]
    )
    return session


def start(agent, **args):
    return Intent(agent=agent, verb=Verb.START, text=args.pop("text", "a project"), args=args)


def test_a_graph_has_common_ideas_and_undiscovered_ones_that_need_them():
    built = graph()
    assert built["idea:radio_repair"].status == "rare"
    transmitter = built["idea:radio_transmitter"]
    assert transmitter.status == "undiscovered"
    assert transmitter.requires == ["idea:radio_repair", "idea:electrical_wiring"]
    assert built["idea:rocket_motor"].difficulty == 4
    assert built["idea:rocket_motor"].requires == [
        "idea:mathematics", "idea:radio_transmitter"
    ]


def test_names_resolve_to_ideas_loosely_but_not_wildly():
    session = with_graph(toy.build_toy())
    state = session.state
    assert knowledge.resolve(state, "idea:rocket_motor") == "idea:rocket_motor"
    assert knowledge.resolve(state, "Radio transmitter") == "idea:radio_transmitter"
    assert knowledge.resolve(state, "radio transmitters") == "idea:radio_transmitter"
    assert knowledge.resolve(state, "teleportation") is None
    assert knowledge.resolve(state, "") is None


def test_learning_needs_the_foundations():
    session = with_graph(toy.build_toy())
    working = session.state.model_copy(deep=True)
    lena = toy.LENA
    with pytest.raises(EffectError, match="lacks"):
        apply_effect(
            working,
            fx.LearnKnowledge(person=lena, idea="idea:radio_transmitter", by="study"),
        )
    # A god may grant anything.
    apply_effect(
        working, fx.LearnKnowledge(person=lena, idea="idea:radio_transmitter", by="god")
    )
    assert knowledge.held(working.entities[lena])["idea:radio_transmitter"] == 1


def test_an_unknown_idea_cannot_be_learned():
    session = with_graph(toy.build_toy())
    working = session.state.model_copy(deep=True)
    with pytest.raises(EffectError, match="no such idea"):
        apply_effect(working, fx.LearnKnowledge(person=toy.ANNA, idea="idea:nothing"))


def test_a_person_starts_a_project_and_it_becomes_a_process_they_own():
    session = with_graph(toy.build_toy())
    verdict = rules.check(
        session.state, start(toy.ANNA, name="Build a new oven", days=3)
    )
    assert verdict.status == "resolved"
    (effect,) = verdict.outcome.effects
    process = effect.process
    assert process.owner == toy.ANNA
    assert process.location == toy.BAKERY
    assert process.work_minutes == 3 * 8 * 60
    assert process.teaches is None


def test_a_project_to_discover_something_needs_the_foundations_held():
    session = with_graph(toy.build_toy())
    state = session.state
    alone = rules.check(state, start(toy.LENA, name="Transmitter", idea="Radio transmitter"))
    assert alone.status == "impossible"
    assert "needs" in alone.reason and "Radio repair" in alone.reason

    ready = rules.check(
        state,
        start(toy.ANNA, name="Transmitter", idea="Radio transmitter", helpers=[toy.LENA]),
    )
    assert ready.status == "resolved"
    process = ready.outcome.effects[0].process
    assert process.teaches == "idea:radio_transmitter"
    # Difficulty sets a floor on how long it takes: 3 * 20 days.
    assert process.work_minutes >= 3 * 20 * 8 * 60


def test_a_large_project_cannot_be_done_alone():
    session = with_graph(toy.build_toy())
    state = session.state
    refused = rules.check(state, start(toy.ANNA, name="A cathedral", days=400))
    assert refused.status == "impossible" and "alone" in refused.reason
    allowed = rules.check(
        state, start(toy.ANNA, name="A cathedral", days=400, helpers=[toy.OTTO])
    )
    assert allowed.status == "resolved"


def test_nonsense_in_a_proposal_is_rejected_not_guessed():
    state = with_graph(toy.build_toy()).state
    for args in (
        {"name": "x", "days": -1},
        {"name": "x", "items": {"item:unobtainium": 1}},
        {"name": "x", "items": {toy.GRAIN: 0}},
        {"name": "x", "helpers": ["person:nobody"]},
        {"name": "x", "idea": "teleportation"},
        {"name": "x", "place": "place:moon"},
    ):
        assert rules.check(state, start(toy.ANNA, **args)).status == "impossible", args


def test_a_person_can_only_carry_two_undertakings():
    session = with_graph(toy.build_toy())
    for n in range(2):
        verdict = rules.check(session.state, start(toy.ANNA, name=f"job {n}", days=1))
        session.commit(
            [EventDraft(actor=toy.ANNA, effects=list(verdict.outcome.effects))]
        )
    third = rules.check(session.state, start(toy.ANNA, name="job 3", days=1))
    assert third.status == "impossible"
    assert len(projects.active_for(session.state, toy.ANNA)) == 2


def test_finishing_a_discovery_teaches_the_workers_and_records_a_fact():
    session = with_graph(toy.build_toy())
    state = session.state
    begun = rules.check(
        state, start(toy.ANNA, name="Transmitter", idea="idea:radio_transmitter",
                     helpers=[toy.LENA])
    )
    session.commit([EventDraft(actor=toy.ANNA, effects=list(begun.outcome.effects))])
    process = next(iter(session.state.processes.values()))
    # Lena has the grounding too, so she takes it in; Otto, who has not, does not.
    session.commit(
        [EventDraft(actor="system", visibility="god_only",
                    effects=[fx.SetAttr(entity=toy.LENA, key="knowledge",
                                        value={"idea:radio_repair": 1,
                                               "idea:electrical_wiring": 1})])]
    )
    # Skip ahead to the last stretch of work.
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[
                    fx.AdvanceProcess(process_id=process.id, delta=0.99),
                    fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY),
                ],
            )
        ]
    )
    work = Intent(agent=toy.ANNA, verb=Verb.WORK, target=process.id, text="work",
                  args={"minutes": 600})
    verdict = rules.check(session.state, work)
    assert verdict.status == "resolved", verdict.reason
    session.commit([EventDraft(actor=toy.ANNA, effects=list(verdict.outcome.effects))])

    final = session.state
    assert final.processes[process.id].status == "completed"
    assert knowledge.held(final.entities[toy.ANNA])["idea:radio_transmitter"] == 3
    assert knowledge.held(final.entities[toy.LENA])["idea:radio_transmitter"] == 2
    assert knowledge.discovered(final, "idea:radio_transmitter")
    assert final.fact_holds("fact:discovered_radio_transmitter")
    assert not check_log(session.store, session.branch_id)

    # Once discovered, it cannot be "discovered" again.
    again = rules.check(
        final, start(toy.ANNA, name="Again", idea="idea:radio_transmitter", helpers=[toy.LENA])
    )
    assert again.status == "impossible" and "already" in again.reason


def test_a_discovery_unlocks_the_next_step_of_the_chain():
    session = with_graph(toy.build_toy())
    # Nobody holds the transmitter, so the rocket motor is out of reach.
    state = session.state
    first = rules.check(
        state, start(toy.ANNA, name="Rocket", idea="Rocket motor", helpers=[toy.OTTO])
    )
    assert first.status == "impossible"
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[
                    fx.LearnKnowledge(person=toy.ANNA, idea="idea:radio_transmitter", by="god"),
                    fx.LearnKnowledge(person=toy.ANNA, idea="idea:mathematics", by="study"),
                ],
            )
        ]
    )
    second = rules.check(
        session.state, start(toy.ANNA, name="Rocket", idea="Rocket motor", helpers=[toy.OTTO])
    )
    assert second.status == "resolved", second.reason


def test_pursuits_lists_only_ideas_a_person_is_ready_for():
    session = with_graph(toy.build_toy())
    state = session.state
    anna = state.entities[toy.ANNA]
    lena = state.entities[toy.LENA]
    assert any("Radio transmitter" in line for line in knowledge.pursuits(state, anna))
    assert not any("Rocket motor" in line for line in knowledge.pursuits(state, anna))
    assert knowledge.pursuits(state, lena) == []


def test_the_prompt_shows_undertakings_and_ideas_to_chase():
    session = with_graph(toy.build_toy())
    lines = projects.lines_for(session.state, session.state.entities[toy.ANNA])
    text = "\n".join(lines)
    assert "use verb start" in text and "Radio transmitter" in text


def test_a_teacher_can_pass_on_an_idea_in_a_scene():
    session = together(with_graph(toy.build_toy()))
    # Lena needs the foundations first; Anna holds the transmitter at level 3.
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[
                    fx.SetAttr(entity=toy.LENA, key="knowledge",
                               value={"idea:radio_repair": 1, "idea:electrical_wiring": 1}),
                    fx.LearnKnowledge(person=toy.ANNA, idea="idea:radio_transmitter",
                                      level=3, by="god"),
                ],
            )
        ]
    )
    from test_scene import simulation, talker

    fake = talker([
        {"say": "Let me show you how it works.", "move": "teach",
         "teach": "Radio transmitter", "tone": "warm"},
        {"say": "I see.", "end": True},
    ])
    # In this scene Lena replies first, so make her the teacher's pupil: swap roles.
    fake.handlers["agent.act"] = lambda request: (
        {"verb": "speak", "text": "talk",
         "say": {"text": "Lena, a word.", "to": [toy.LENA]}}
        if request.context.agent == toy.ANNA else {"verb": "wait", "text": "wait"}
    )
    # Lena speaks the first scene turn; have her teach nothing, then Anna teach.
    lines = iter([
        {"say": "What is it?", "tone": "neutral"},
        {"say": "Let me show you how it works.", "move": "teach",
         "teach": "Radio transmitter", "tone": "warm"},
        {"say": "I see.", "end": True},
    ])
    fake.handlers["agent.scene"] = lambda request: next(lines, {"say": "", "end": True})
    run(simulation(session, fake).tick(15))
    assert knowledge.level(session.state, session.state.entities[toy.LENA],
                           "idea:radio_transmitter") == 2


def test_nobody_can_be_taught_what_they_are_not_ready_for():
    session = together(with_graph(toy.build_toy()))
    from tinyworld.sim.scene import Scenes

    class Stub:
        pass

    sim = Stub()
    sim.session = session
    sim.write_notes = lambda *a, **k: None
    scenes = Scenes(sim)
    session.commit(
        [EventDraft(actor="system", visibility="god_only",
                    effects=[fx.LearnKnowledge(person=toy.ANNA, idea="idea:radio_transmitter",
                                               level=3, by="god")])]
    )
    state = session.state
    events = scenes._teach(
        state.entities[toy.ANNA], state.entities[toy.LENA], "Radio transmitter"
    )
    assert events == []
    assert knowledge.level(session.state, session.state.entities[toy.LENA],
                           "idea:radio_transmitter") == 0
