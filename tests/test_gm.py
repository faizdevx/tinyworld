import asyncio

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft, Intent, Utterance, Verb
from tinyworld.core.state import Fact, Process, ProcessRequirements
from tinyworld.fixtures import toy
from tinyworld.gm import conflicts, rules
from tinyworld.gm.adjudicator import Adjudicator, check_effects
from tinyworld.gm.master import GameMaster
from tinyworld.gm.perception import limit_attention, perceive
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.step import apply_intents


def run(coroutine):
    return asyncio.run(coroutine)


def gm_with(fake, session=None):
    tracer = Tracer(session.store, LLMConfig()) if session else None
    return GameMaster(Adjudicator(StructuredLLM(fake, LLMConfig(), tracer)), seed="test")


def intent(agent, verb, target=None, text="", **args):
    utterance = args.pop("utterance", None)
    return Intent(agent=agent, verb=verb, target=target, args=args, text=text, utterance=utterance)


def say(text, *addressees, channel="direct", claims=()):
    return Utterance(text=text, addressees=list(addressees), channel=channel, claims=list(claims))


# -- rules -------------------------------------------------------------------


def test_move_follows_the_graph_and_costs_travel_time():
    state = toy.build_toy().state
    verdict = rules.check(state, intent(toy.LENA, Verb.MOVE, toy.BACK_ROOM))
    assert verdict.status == "resolved"
    assert verdict.outcome.minutes == 43
    assert verdict.outcome.effects == [fx.MoveEntity(entity=toy.LENA, to=toy.BACK_ROOM)]


@pytest.mark.parametrize(
    "bad, reason",
    [
        (intent(toy.ANNA, Verb.MOVE, "place:moon"), "not a place"),
        (intent(toy.ANNA, Verb.MOVE, toy.BAKERY), "already at"),
        (intent(toy.ANNA, Verb.MOVE, toy.OTTO), "not a place"),
        (intent("person:ghost", Verb.WAIT), "no such person"),
        (intent(toy.ANNA, Verb.GIVE, toy.OTTO, item=toy.BREAD), "not here"),
        (intent(toy.ANNA, Verb.GIVE, toy.BAKERY, item=toy.BREAD, quantity=50), "does not have"),
        (intent(toy.ANNA, Verb.GIVE, toy.BAKERY, item="resource:gold"), "no such item"),
        (intent(toy.ANNA, Verb.GIVE, toy.BAKERY, item=toy.BREAD, quantity=-1), "positive"),
        (intent(toy.ANNA, Verb.TAKE, toy.BAKERY, item=toy.GRAIN), "there is not"),
        (intent(toy.ANNA, Verb.TAKE, toy.FARM, item=toy.GRAIN), "not within reach"),
        (intent(toy.ANNA, Verb.ATTACK, toy.OTTO), "not here"),
        (intent(toy.ANNA, Verb.USE, "item:oven"), "there is no"),
        (intent(toy.ANNA, Verb.SPEAK), "nothing to say"),
        (intent(toy.ANNA, Verb.SPEAK, utterance=say("Hello", toy.OTTO)), "not here"),
        (intent(toy.ANNA, Verb.WAIT, minutes=0), "positive"),
    ],
)
def test_impossible_intents_are_rejected_by_rules(bad, reason):
    verdict = rules.check(toy.build_toy().state, bad)
    assert verdict.status == "impossible"
    assert reason in verdict.reason


def test_the_dead_cannot_act():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.Kill(entity=toy.ANNA)])])
    verdict = rules.check(session.state, intent(toy.ANNA, Verb.WAIT))
    assert verdict.status == "impossible" and "dead" in verdict.reason


def test_give_and_free_take_are_resolved_without_a_model():
    state = toy.build_toy().state
    give = rules.check(state, intent(toy.ANNA, Verb.GIVE, toy.BAKERY, item=toy.BREAD, quantity=2))
    take = rules.check(state, intent(toy.ANNA, Verb.TAKE, toy.BAKERY, item=toy.BREAD, quantity=3))
    assert give.status == take.status == "resolved"
    assert take.outcome.effects[0].dest == toy.ANNA


def test_taking_from_a_person_or_owned_place_needs_adjudication():
    session = toy.build_toy()
    session.commit(
        [
            EventDraft(
                actor="system",
                effects=[
                    fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY),
                    fx.SetAttr(entity=toy.BAKERY, key="owner", value=toy.ANNA),
                ],
            )
        ]
    )
    state = session.state
    assert rules.check(state, intent(toy.LENA, Verb.TAKE, toy.ANNA, item=toy.COIN)).status == "adjudicate"
    assert rules.check(state, intent(toy.LENA, Verb.TAKE, toy.BAKERY, item=toy.BREAD)).status == "adjudicate"
    assert rules.check(state, intent(toy.ANNA, Verb.TAKE, toy.BAKERY, item=toy.BREAD)).status == "resolved"


def test_speech_rides_along_with_another_action():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY)])])
    verdict = rules.check(
        session.state,
        intent(toy.ANNA, Verb.GIVE, toy.LENA, item=toy.BREAD, utterance=say("Take this.", toy.LENA)),
    )
    assert [type(e).__name__ for e in verdict.outcome.effects] == ["Utter", "TransferItem"]


def _oven(**requirements):
    return Process(
        id="process:new_oven",
        name="building a new oven",
        owner=toy.ANNA,
        location=toy.BAKERY,
        work_minutes=120,
        requirements=ProcessRequirements(**requirements),
        outcome=Fact(id="fact:new_oven", text="The bakery has a second oven."),
    )


def test_work_on_a_process_checks_requirements_and_completes_it():
    session = toy.build_toy()
    session.commit(
        [EventDraft(actor="system", effects=[fx.StartProcess(process=_oven(items={toy.GRAIN: 1}, participants=[toy.LENA]))])]
    )
    work = intent(toy.ANNA, Verb.WORK, "process:new_oven", minutes=60)
    blocked = rules.check(session.state, work)
    assert blocked.status == "impossible"
    assert "Lena Vogel is not present" in blocked.reason and "needs 1 grain" in blocked.reason

    session.commit(
        [
            EventDraft(
                actor="system",
                effects=[
                    fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY),
                    fx.ChangeQuantity(holder=toy.BAKERY, item=toy.GRAIN, delta=1),
                ],
            )
        ]
    )
    gm = GameMaster(seed="t")
    run(apply_intents(session, gm, [work]))
    assert session.state.processes["process:new_oven"].progress == 0.5
    result = run(apply_intents(session, gm, [work]))
    assert session.state.processes["process:new_oven"].status == "completed"
    assert session.state.fact_holds("fact:new_oven")
    assert "completes" in result.events[0].narration

    assert rules.check(session.state, work).status == "impossible"


# -- game master -------------------------------------------------------------


def test_rule_resolved_intents_never_call_the_model():
    session = toy.build_toy()
    fake = FakeLLM()
    result = run(
        apply_intents(
            session,
            gm_with(fake),
            [
                intent(toy.ANNA, Verb.MOVE, toy.SQUARE),
                intent(toy.OTTO, Verb.MOVE, "place:moon"),
                intent(toy.LENA, Verb.WAIT),
            ],
        )
    )
    assert fake.calls == []
    assert [o.status for o in result.outcomes] == ["success", "impossible", "success"]
    assert len(result.events) == 2
    assert session.state.entities[toy.ANNA].location == toy.SQUARE
    assert session.state.entities[toy.OTTO].location == toy.TOWN_HALL


def test_contention_for_the_last_item_is_settled_by_rules():
    session = toy.build_toy()
    session.commit(
        [
            EventDraft(
                actor="system",
                effects=[
                    fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY),
                    fx.ChangeQuantity(holder=toy.BAKERY, item=toy.BREAD, delta=-19),
                ],
            )
        ]
    )
    result = run(
        apply_intents(
            session,
            GameMaster(seed="t"),
            [
                intent(toy.ANNA, Verb.TAKE, toy.BAKERY, item=toy.BREAD),
                intent(toy.LENA, Verb.TAKE, toy.BAKERY, item=toy.BREAD),
            ],
        )
    )
    assert sorted(o.status for o in result.outcomes) == ["impossible", "success"]
    assert toy.BREAD not in session.state.entities[toy.BAKERY].inventory
    loser = next(o for o in result.outcomes if o.status == "impossible")
    notes = [o for o in result.observations if o.observer == loser.intent.agent and "could not" in o.text]
    assert len(notes) == 1


def _both_in_bakery(session):
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY)])])


def test_adjudicated_outcome_is_applied():
    session = toy.build_toy()
    _both_in_bakery(session)
    fake = FakeLLM(
        {
            "gm.adjudicate": {
                "status": "success",
                "effects": [
                    {"type": "TransferItem", "item": toy.COIN, "quantity": 2, "source": toy.ANNA, "dest": toy.LENA},
                    {"type": "SetRelation", "source": toy.ANNA, "dest": toy.LENA, "kind": "wary", "value": 20},
                ],
                "narration": "Lena talks Anna into an advance on her wages.",
                "minutes": 5,
            }
        }
    )
    result = run(
        apply_intents(
            session, gm_with(fake, session),
            [intent(toy.LENA, Verb.TAKE, toy.ANNA, text="ask for an advance", item=toy.COIN, quantity=2)],
        )
    )
    assert result.outcomes[0].status == "success"
    assert session.state.entities[toy.LENA].inventory[toy.COIN] == 5
    assert session.state.relation(toy.ANNA, toy.LENA).value == 20
    assert result.events[0].trace_id is not None
    prompt = fake.calls[0].user
    assert "Keller Bakery" in prompt and "ask for an advance" in prompt
    assert "MoveEntity" in fake.calls[0].stable_context


@pytest.mark.parametrize(
    "effect, why",
    [
        ({"type": "Teleport", "entity": toy.LENA, "to": toy.FARM}, "vocabulary"),
        ({"type": "SetRule", "key": "gravity", "value": 0}, "forbidden"),
        ({"type": "AdvanceTime", "minutes": 600}, "forbidden"),
        ({"type": "Kill", "entity": toy.OTTO}, "out of reach"),
        ({"type": "MoveEntity", "entity": toy.LENA, "to": toy.FARM}, "not adjacent"),
        ({"type": "TransferItem", "item": toy.COIN, "quantity": 500, "source": toy.ANNA, "dest": toy.LENA}, "does not apply"),
        ({"type": "SetAttr", "entity": toy.ANNA, "key": "persona", "value": {}}, "protected"),
        (
            {"type": "CreateEntity", "entity": {"id": "person:helper", "kind": "person", "name": "Helper", "location": toy.BAKERY}},
            "people cannot be created",
        ),
    ],
)
def test_unacceptable_adjudications_are_refused_and_change_nothing(effect, why):
    session = toy.build_toy()
    _both_in_bakery(session)
    before = session.state.model_dump()
    fake = FakeLLM({"gm.adjudicate": {"status": "success", "effects": [effect], "narration": "It works."}})
    result = run(apply_intents(session, gm_with(fake), [intent(toy.LENA, Verb.OTHER, text="do something clever")]))

    assert len(fake.calls) == 3, why
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].effects == []
    after = session.state.model_dump()
    assert after["entities"] == before["entities"] and after["rules"] == before["rules"]
    assert result.events[0].effects == []


def test_failed_adjudication_may_not_carry_effects():
    session = toy.build_toy()
    _both_in_bakery(session)
    fake = FakeLLM(
        {
            "gm.adjudicate": [
                {"status": "failed", "effects": [{"type": "Kill", "entity": toy.ANNA}]},
                {"status": "failed", "narration": "Anna shoves Lena away.", "reason": "Anna is stronger"},
            ]
        }
    )
    result = run(apply_intents(session, gm_with(fake), [intent(toy.LENA, Verb.ATTACK, toy.ANNA)]))
    assert result.outcomes[0].status == "failed"
    assert session.state.entities[toy.ANNA].alive
    assert result.events[0].narration == "Anna shoves Lena away."


def test_without_a_model_adjudicated_intents_fail_cleanly():
    session = toy.build_toy()
    _both_in_bakery(session)
    result = run(apply_intents(session, GameMaster(), [intent(toy.LENA, Verb.ATTACK, toy.ANNA)]))
    assert result.outcomes[0].status == "failed"
    assert "no Game Master model" in result.outcomes[0].reason


def test_interfering_intents_are_decided_together():
    session = toy.build_toy()
    _both_in_bakery(session)
    fake = FakeLLM(
        {
            "gm.conflict": {
                "outcomes": [
                    {"agent": toy.LENA, "status": "failed", "narration": "Lena swings and misses."},
                    {
                        "agent": toy.ANNA,
                        "status": "success",
                        "effects": [{"type": "SetAttr", "entity": toy.LENA, "key": "health", "value": 60}],
                        "narration": "Anna knocks Lena down.",
                        "loud": True,
                    },
                ]
            }
        }
    )
    result = run(
        apply_intents(
            session, gm_with(fake),
            [intent(toy.LENA, Verb.ATTACK, toy.ANNA), intent(toy.ANNA, Verb.ATTACK, toy.LENA)],
        )
    )
    assert [c.role for c in fake.calls] == ["gm.conflict"]
    assert [o.status for o in result.outcomes] == ["failed", "success"]
    assert session.state.entities[toy.LENA].attrs["health"] == 60


def test_group_adjudication_must_cover_every_actor():
    session = toy.build_toy()
    _both_in_bakery(session)
    fake = FakeLLM({"gm.conflict": {"outcomes": [{"agent": toy.LENA, "status": "success"}]}})
    result = run(
        apply_intents(
            session, gm_with(fake),
            [intent(toy.LENA, Verb.ATTACK, toy.ANNA), intent(toy.ANNA, Verb.ATTACK, toy.LENA)],
        )
    )
    assert [o.status for o in result.outcomes] == ["failed", "failed"]


def test_independent_intents_are_adjudicated_separately():
    state = toy.build_toy().state
    groups = conflicts.group(
        state,
        [
            intent(toy.ANNA, Verb.USE, toy.BAKERY),
            intent(toy.OTTO, Verb.OTHER, text="write a decree"),
            intent(toy.LENA, Verb.MAKE, toy.FARM),
        ],
    )
    assert [len(g) for g in groups] == [1, 1, 1]


def test_shared_targets_group_intents():
    session = toy.build_toy()
    _both_in_bakery(session)
    state = session.state
    same_goods = conflicts.group(
        state,
        [
            intent(toy.ANNA, Verb.TAKE, toy.BAKERY, item=toy.BREAD),
            intent(toy.LENA, Verb.TAKE, toy.BAKERY, item=toy.BREAD),
            intent(toy.OTTO, Verb.OTHER),
        ],
    )
    assert sorted(len(g) for g in same_goods) == [1, 2]
    different_goods = conflicts.group(
        state,
        [
            intent(toy.ANNA, Verb.TAKE, toy.BAKERY, item=toy.BREAD),
            intent(toy.LENA, Verb.TAKE, toy.BAKERY, item=toy.COIN),
        ],
    )
    assert [len(g) for g in different_goods] == [1, 1]
    acted_upon = conflicts.group(
        state,
        [intent(toy.LENA, Verb.OTHER, toy.ANNA), intent(toy.ANNA, Verb.OTHER)],
    )
    assert [len(g) for g in acted_upon] == [2]


def test_check_effects_allows_a_move_to_a_neighbour_and_item_creation():
    state = toy.build_toy().state
    assert check_effects(state, [toy.ANNA], [fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE)]) is None
    made = fx.CreateEntity(
        entity={"id": "item:rye_loaf", "kind": "item", "name": "rye loaf", "location": toy.BAKERY}
    )
    assert check_effects(state, [toy.ANNA], [made]) is None


# -- perception --------------------------------------------------------------


def commit_one(session, **kwargs):
    result = session.commit([EventDraft(**kwargs)], observe=perceive)
    return {o.observer: o for o in result.observed[0]}


def test_event_in_a_closed_room_is_not_observed_from_outside():
    session = toy.build_toy()
    session.commit(
        [
            EventDraft(
                actor="system",
                effects=[
                    fx.MoveEntity(entity=toy.ANNA, to=toy.BACK_ROOM),
                    fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY),
                    fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE),
                ],
            )
        ]
    )
    seen = commit_one(
        session,
        actor=toy.ANNA,
        location=toy.BACK_ROOM,
        effects=[fx.TransferItem(item=toy.GRAIN, quantity=2, source=toy.BACK_ROOM, dest=toy.ANNA)],
        narration="Anna Keller hides two sacks of grain under her coat.",
        loud=True,
    )
    assert set(seen) == {toy.ANNA}
    assert seen[toy.ANNA].mode == "self" and seen[toy.ANNA].confidence == 1.0


def test_loud_event_is_heard_next_door_with_lower_confidence():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.LENA, to=toy.TAVERN)])])
    seen = commit_one(
        session,
        actor=toy.OTTO,
        location=toy.TOWN_HALL,
        effects=[],
        narration="Otto Brandt smashes a chair against the wall.",
        loud=True,
    )
    assert seen[toy.OTTO].mode == "self"
    assert toy.LENA not in seen and toy.ANNA not in seen

    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.LENA, to=toy.SQUARE)])])
    seen = commit_one(
        session, actor=toy.OTTO, location=toy.TOWN_HALL,
        narration="Otto Brandt smashes a chair against the wall.", loud=True,
    )
    heard = seen[toy.LENA]
    assert heard.mode == "auditory" and heard.confidence == 0.5
    assert "commotion" in heard.text and "Otto" not in heard.text
    assert heard.participants == []


def test_quiet_event_is_seen_but_not_heard_across_a_visible_edge():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE)])])
    seen = commit_one(
        session, actor=toy.ANNA, location=toy.BAKERY,
        narration="Anna Keller sweeps the floor.",
    )
    assert seen[toy.OTTO].mode == "visual" and seen[toy.OTTO].confidence == 0.6
    assert toy.LENA not in seen


def _gossip(channel, *addressees):
    return fx.Utter(
        speaker=toy.ANNA,
        text="The mayor is hoarding grain.",
        addressees=list(addressees),
        channel=channel,
        claims=[fx.Claim(subject=toy.OTTO, predicate="hoards", value="grain")],
    )


def test_private_speech_reaches_the_addressee_and_is_only_overheard_by_bystanders():
    session = toy.build_toy()
    session.commit(
        [
            EventDraft(
                actor="system",
                effects=[
                    fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY),
                    fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE),
                    fx.CreateEntity(entity={"id": "person:eve", "kind": "person", "name": "Eve", "location": toy.BAKERY}),
                ],
            )
        ]
    )
    seen = commit_one(
        session, kind="utterance", actor=toy.ANNA, location=toy.BAKERY,
        effects=[_gossip("direct", toy.LENA)],
        narration='Anna Keller says to Lena Vogel: "The mayor is hoarding grain."',
    )
    assert seen[toy.LENA].addressed and seen[toy.LENA].confidence == 1.0
    assert seen[toy.LENA].claims[0].predicate == "hoards"
    assert seen["person:eve"].mode == "auditory" and seen["person:eve"].confidence == 0.7
    # Across the square Otto sees them talking but catches no words.
    assert seen[toy.OTTO].claims == [] and "hoarding" not in seen[toy.OTTO].text


def test_shouted_speech_carries_its_words_next_door():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE)])])
    seen = commit_one(
        session, kind="utterance", actor=toy.ANNA, location=toy.BAKERY,
        effects=[_gossip("audible")],
        narration='Anna Keller says: "The mayor is hoarding grain."',
    )
    assert "hoarding" in seen[toy.OTTO].text
    assert seen[toy.OTTO].claims and seen[toy.OTTO].confidence == 0.6
    assert toy.LENA not in seen


def test_arrival_is_seen_at_both_ends():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE)])])
    result = run(apply_intents(session, GameMaster(), [intent(toy.OTTO, Verb.MOVE, toy.TOWN_HALL)]))
    # Anna watches him leave the square through the bakery window.
    seen = {o.observer: o for o in result.observations}
    assert set(seen) == {toy.OTTO, toy.ANNA}
    assert seen[toy.ANNA].confidence == 0.6

    run(apply_intents(session, GameMaster(), [intent(toy.ANNA, Verb.MOVE, toy.TAVERN)]))
    result = run(apply_intents(session, GameMaster(), [intent(toy.OTTO, Verb.MOVE, toy.SQUARE)]))
    assert {o.observer for o in result.observations} == {toy.OTTO}

    # Lena walks in from the farm: Otto, already in the square, sees her arrive.
    result = run(apply_intents(session, GameMaster(), [intent(toy.LENA, Verb.MOVE, toy.SQUARE)]))
    seen = {o.observer: o for o in result.observations}
    assert seen[toy.OTTO].mode == "visual" and seen[toy.OTTO].confidence == 1.0


def test_visibility_levels():
    session = toy.build_toy()
    assert commit_one(session, actor="god", visibility="god_only", narration="x") == {}
    public = commit_one(session, actor="system", visibility="public", narration="Church bells ring.")
    assert set(public) == {toy.ANNA, toy.OTTO, toy.LENA}
    assert all(o.mode == "public" for o in public.values())

    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY)])])
    session.commit(
        [EventDraft(actor="system", effects=[fx.CreateEntity(entity={"id": "person:eve", "kind": "person", "name": "Eve", "location": toy.BAKERY})])]
    )
    secret = commit_one(
        session, actor=toy.ANNA, location=toy.BAKERY, visibility="secret",
        effects=[fx.TransferItem(item=toy.COIN, quantity=1, source=toy.ANNA, dest=toy.LENA)],
        narration="Anna slips Lena a coin.",
    )
    assert set(secret) == {toy.ANNA, toy.LENA}


def test_the_dead_perceive_nothing():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.Kill(entity=toy.LENA)])])
    public = commit_one(session, actor="system", visibility="public", narration="Bells ring.")
    assert toy.LENA not in public


def test_attention_limit_keeps_the_most_salient_in_time_order():
    session = toy.build_toy()
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY)])])
    observations = []
    for index in range(6):
        result = session.commit(
            [EventDraft(actor=toy.ANNA, location=toy.BAKERY, narration=f"Anna does thing {index}.")],
            observe=perceive,
        )
        observations += [o for o in result.observed[0] if o.observer == toy.LENA]
    result = session.commit(
        [
            EventDraft(
                kind="utterance", actor=toy.ANNA, location=toy.BAKERY,
                effects=[_gossip("direct", toy.LENA)], narration="Anna speaks to Lena.",
            )
        ],
        observe=perceive,
    )
    observations += [o for o in result.observed[0] if o.observer == toy.LENA]

    kept = limit_attention(observations, 3)
    assert len(kept) == 3
    assert kept[-1].addressed
    assert [o.event_seq for o in kept] == sorted(o.event_seq for o in kept)
    assert limit_attention(observations, 0) == []
