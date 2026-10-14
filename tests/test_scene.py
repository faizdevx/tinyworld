import asyncio
from datetime import timedelta

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.eval.invariants import check_log
from tinyworld.fixtures import toy
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.sim import commitments as pledges
from tinyworld.sim.loop import Simulation
from tinyworld.sim.scene import openings
from test_routine import quiet_llm, run


def talker(script):
    """Anna greets Lena; scene lines come from ``script`` in order."""
    lines = iter(script)

    def scene(request):
        try:
            return next(lines)
        except StopIteration:
            return {"say": "", "end": True}

    def act(request):
        if request.context.agent == toy.ANNA:
            return {
                "verb": "speak", "text": "talk to Lena",
                "say": {"text": "Lena, a word.", "to": [toy.LENA]},
            }
        return {"verb": "wait", "text": "wait"}

    base = quiet_llm()
    base.handlers["agent.act"] = act
    base.handlers["agent.scene"] = scene
    return base


def together(session):
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY)],
            )
        ]
    )
    return session


def simulation(session, fake):
    llm = StructuredLLM(fake, LLMConfig(), Tracer(session.store, LLMConfig()))
    return Simulation(session, llm, routines=False)


def test_a_line_to_someone_is_answered_inside_the_same_tick():
    session = together(toy.build_toy())
    fake = talker([
        {"say": "What is it, Anna?", "tone": "neutral"},
        {"say": "Never mind.", "end": True},
    ])
    sim = simulation(session, fake)
    result = run(sim.tick(15))
    assert result.scenes == 1
    assert result.scene_turns >= 1
    said = [
        e for e in result.events
        if any(isinstance(x, fx.Utter) and x.speaker == toy.LENA for x in e.effects)
    ]
    assert said


def test_a_promise_in_a_scene_becomes_a_commitment_and_is_kept_or_broken():
    session = together(toy.build_toy())
    fake = talker([
        {
            "say": "Come to the tavern tonight.", "move": "promise", "tone": "warm",
            "promise": {"kind": "meet", "text": "meet at the tavern",
                        "place": toy.TAVERN, "hours": 2},
        },
        {"say": "Fine.", "end": True},
    ])
    sim = simulation(session, fake)
    result = run(sim.tick(15))
    assert result.commitments_made == 1
    (promise,) = session.state.open_commitments()
    assert promise.by == toy.LENA and promise.to == toy.ANNA
    assert pledges.lines_for(session.state, toy.LENA)

    # Time passes with Lena somewhere else: the promise is broken and trust falls.
    before = session.state.relation(toy.ANNA, toy.LENA).value
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[fx.AdvanceTime(minutes=180)],
            )
        ]
    )
    settled = sim.settle_commitments()
    assert settled
    assert session.state.commitments[promise.id].status == "broken"
    assert session.state.relation(toy.ANNA, toy.LENA).value < before
    assert not check_log(session.store, session.branch_id)


def test_a_promise_to_meet_is_kept_when_the_person_is_there():
    session = together(toy.build_toy())
    fake = talker([
        {
            "say": "Meet me at the square.", "move": "promise",
            "promise": {"kind": "meet", "text": "be at the square",
                        "place": toy.SQUARE, "hours": 1},
        },
        {"say": "Fine.", "end": True},
    ])
    sim = simulation(session, fake)
    run(sim.tick(15))
    session.commit(
        [
            EventDraft(
                actor="system", visibility="god_only",
                effects=[
                    fx.MoveEntity(entity=toy.LENA, to=toy.SQUARE),
                    fx.AdvanceTime(minutes=90),
                ],
            )
        ]
    )
    sim.settle_commitments()
    assert [c.status for c in session.state.commitments.values()] == ["kept"]


def test_a_promise_to_a_place_that_does_not_exist_is_dropped():
    session = together(toy.build_toy())
    fake = talker([
        {
            "say": "Meet me at the moon.", "move": "promise",
            "promise": {"kind": "meet", "text": "moon", "place": "place:moon", "hours": 1},
        },
        {"end": True, "say": "ok"},
    ])
    result = run(simulation(session, fake).tick(15))
    assert result.commitments_made == 0
    assert not session.state.commitments


def test_a_scene_never_runs_past_its_turn_limit():
    session = together(toy.build_toy())
    fake = talker([{"say": "and another thing", "tone": "angry"}] * 20)
    sim = simulation(session, fake)
    result = run(sim.tick(15))
    assert result.scene_turns <= sim.scenes.max_turns


def test_a_dead_listener_gets_no_scene():
    session = together(toy.build_toy())
    session.commit(
        [EventDraft(actor="system", visibility="god_only",
                    effects=[fx.Kill(entity=toy.LENA, cause="test")])]
    )
    result = run(simulation(session, talker([{"say": "hm"}])).tick(15))
    assert result.scenes == 0


def test_openings_pick_one_scene_per_pair():
    session = together(toy.build_toy())
    event = session.commit(
        [
            EventDraft(
                actor=toy.ANNA, kind="utterance", location=toy.BAKERY,
                effects=[
                    fx.Utter(speaker=toy.ANNA, text="hello", addressees=[toy.LENA],
                             channel="direct", message_type="tell")
                ],
            )
        ]
    ).events
    found = openings(session.state, event, limit=4)
    assert found == [(toy.ANNA, toy.LENA, "hello")]


def test_a_scene_world_replays_identically():
    session = together(toy.build_toy())
    start = session.state.seq
    fake = talker([
        {
            "say": "Come tonight.", "move": "promise",
            "promise": {"kind": "meet", "text": "tavern", "place": toy.TAVERN, "hours": 3},
        },
        {"say": "Fine.", "end": True},
    ])
    run(simulation(session, fake).tick(15))
    recorded = session.store.events(session.branch_id, after=start)
    assert any(isinstance(x, fx.MakeCommitment) for e in recorded for x in e.effects)

    replay = session.fork(start, "replay")
    llm = StructuredLLM(
        ReplayLLM(session.store, session.branch_id), LLMConfig(),
        Tracer(session.store, LLMConfig()),
    )
    run(Simulation(replay, llm, routines=False).tick(15))
    replayed = session.store.events(replay.branch_id, after=start)

    def effects_of(events):
        return [[x.model_dump_json() for x in e.effects] for e in events]

    assert effects_of(replayed) == effects_of(recorded)
