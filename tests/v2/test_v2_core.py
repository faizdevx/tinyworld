import random
from datetime import datetime

import pytest

from tinyworld.core import branches
from tinyworld.core import effects as fx
from tinyworld.core.events import Event, EventDraft
from tinyworld.core.ids import edge_key, make_id, parse_id
from tinyworld.core.reducers import EffectError, apply_effects, apply_event, fold
from tinyworld.core.session import CommitError, WorldSession
from tinyworld.core.state import Entity, Fact, PlaceEdge, Process, WorldState
from tinyworld.core.store import Store, StoreError
from tinyworld.core.time import parse_step
from tinyworld.fixtures import toy


def draft(*effects, actor="system", **kwargs):
    return EventDraft(actor=actor, effects=list(effects), **kwargs)


# -- ids and time ------------------------------------------------------------


def test_ids_round_trip():
    assert make_id("person", "Anna Keller") == "person:anna_keller"
    assert parse_id("place:market_square") == ("place", "market_square")
    assert edge_key("place:b", "place:a") == edge_key("place:a", "place:b")


@pytest.mark.parametrize("bad", ["anna", "npc:anna", "person:", "person:Anna", 5])
def test_invalid_ids_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_id(bad)


def test_entity_id_must_match_kind():
    with pytest.raises(ValueError):
        Entity(id="place:x", kind="person", name="X")


def test_parse_step_covers_minutes_to_years():
    assert parse_step("15m") == 15
    assert parse_step("6h") == 360
    assert parse_step("20y") == 20 * 365 * 24 * 60
    with pytest.raises(ValueError):
        parse_step("soon")


# -- reducers ----------------------------------------------------------------


def test_toy_world_builds():
    state = toy.build_toy().state
    assert len(state.people()) == 3
    assert state.entities[toy.ANNA].location == toy.BAKERY
    assert state.entities[toy.BACK_ROOM].inventory[toy.GRAIN] == 6
    assert state.fact_holds("fact:grain_rationed")
    assert state.path(toy.FARM, toy.BACK_ROOM) == (
        [toy.FARM, toy.SQUARE, toy.BAKERY, toy.BACK_ROOM],
        43,
    )


def test_transfer_moves_quantity_and_conserves_total():
    state = toy.build_toy().state
    after = apply_effects(
        state,
        [fx.TransferItem(item=toy.COIN, quantity=5, source=toy.OTTO, dest=toy.ANNA)],
    )
    assert after.entities[toy.OTTO].inventory[toy.COIN] == 55
    assert after.entities[toy.ANNA].inventory[toy.COIN] == 17
    assert state.entities[toy.OTTO].inventory[toy.COIN] == 60


@pytest.mark.parametrize(
    "effect",
    [
        fx.MoveEntity(entity=toy.ANNA, to="place:nowhere"),
        fx.MoveEntity(entity=toy.ANNA, to=toy.OTTO),
        fx.MoveEntity(entity=toy.BAKERY, to=toy.SQUARE),
        fx.TransferItem(item=toy.COIN, quantity=999, source=toy.ANNA, dest=toy.OTTO),
        fx.TransferItem(item=toy.LENA, quantity=1, source=toy.ANNA, dest=toy.OTTO),
        fx.ChangeQuantity(holder=toy.ANNA, item=toy.BREAD, delta=-3),
        fx.SetAttr(entity=toy.ANNA, key="superpower", value="flight"),
        fx.SetAttr(entity=toy.ANNA, key="age", value="old"),
        fx.CreateEntity(entity=Entity(id=toy.ANNA, kind="person", name="Twin")),
        fx.RemoveEntity(entity=toy.BAKERY),
        fx.Kill(entity=toy.BAKERY),
        fx.SetRelation(source=toy.ANNA, dest=toy.ANNA, value=10),
        fx.SetEdge(a=toy.SQUARE, b=toy.SQUARE, edge=PlaceEdge()),
        fx.RetractFact(fact_id="fact:unknown"),
        fx.AdvanceProcess(process_id="process:none", delta=0.1),
        fx.SetRule(key="__class__", value=1),
    ],
)
def test_structurally_invalid_effects_are_rejected(effect):
    state = toy.build_toy().state
    with pytest.raises(EffectError):
        apply_effects(state, [effect])


def test_the_dead_cannot_be_killed_twice_or_speak():
    state = apply_effects(toy.build_toy().state, [fx.Kill(entity=toy.OTTO)])
    assert state.entities[toy.OTTO].alive is False
    with pytest.raises(EffectError):
        apply_effects(state, [fx.Kill(entity=toy.OTTO)])
    with pytest.raises(EffectError):
        apply_effects(state, [fx.Utter(speaker=toy.OTTO, text="Hello")])


def test_remove_entity_cleans_references():
    state = apply_effects(toy.build_toy().state, [fx.RemoveEntity(entity=toy.LENA)])
    assert toy.LENA not in state.entities
    assert all(toy.LENA not in key for key in state.relations)


def test_retracted_fact_stops_holding_but_is_kept():
    state = apply_effects(
        toy.build_toy().state, [fx.RetractFact(fact_id="fact:grain_rationed")]
    )
    assert not state.fact_holds("fact:grain_rationed")
    assert "fact:grain_rationed" in state.facts


def test_process_lifecycle():
    process = Process(id="process:new_oven", name="Build a new oven", owner=toy.ANNA)
    state = apply_effects(
        toy.build_toy().state,
        [
            fx.StartProcess(process=process),
            fx.AdvanceProcess(process_id=process.id, delta=0.7),
            fx.AdvanceProcess(process_id=process.id, delta=0.7),
        ],
    )
    assert state.processes[process.id].progress == 1.0
    state = apply_effects(state, [fx.EndProcess(process_id=process.id, status="completed")])
    with pytest.raises(EffectError):
        apply_effects(state, [fx.AdvanceProcess(process_id=process.id, delta=0.1)])


def test_event_applies_all_effects_or_none():
    session = toy.build_toy()
    before = session.state.model_dump()
    event = Event(
        branch_id=session.branch_id,
        seq=session.state.seq + 1,
        sim_time=session.state.sim_time,
        actor="system",
        effects=[
            fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE),
            fx.MoveEntity(entity=toy.ANNA, to="place:nowhere"),
        ],
    )
    with pytest.raises(EffectError):
        apply_event(session.state, event)
    assert session.state.model_dump() == before


def test_events_must_arrive_in_sequence():
    session = toy.build_toy()
    event = Event(
        branch_id=session.branch_id,
        seq=session.state.seq + 2,
        sim_time=session.state.sim_time,
        actor="system",
    )
    with pytest.raises(EffectError):
        apply_event(session.state, event)


def test_time_advances_and_is_stamped_on_later_events():
    session = toy.build_toy()
    result = session.commit(
        [
            draft(fx.AdvanceTime(minutes=90)),
            draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE), actor=toy.ANNA),
        ]
    )
    # An event carries the time at which it is over.
    assert result.events[0].sim_time == datetime(1943, 3, 14, 9, 30)
    assert result.events[1].sim_time == datetime(1943, 3, 14, 9, 30)
    assert session.state.sim_time == datetime(1943, 3, 14, 9, 30)


# -- session and store -------------------------------------------------------


def test_atomic_commit_stores_nothing_on_failure():
    session = toy.build_toy()
    head = session.state.seq
    with pytest.raises(CommitError):
        session.commit(
            [
                draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE)),
                draft(fx.Kill(entity=toy.BAKERY)),
            ]
        )
    assert session.state.seq == head
    assert session.store.head_seq(session.branch_id) == head
    assert session.state.entities[toy.ANNA].location == toy.BAKERY


def test_non_atomic_commit_skips_only_the_bad_draft():
    session = toy.build_toy()
    result = session.commit(
        [
            draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE)),
            draft(fx.MoveEntity(entity=toy.LENA, to=toy.SQUARE), fx.Kill(entity=toy.BAKERY)),
            draft(fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE)),
        ],
        atomic=False,
    )
    assert len(result.events) == 2
    assert len(result.rejected) == 1
    assert [e.seq for e in result.events] == [8, 9]
    assert session.state.entities[toy.LENA].location == toy.FARM
    assert session.state.entities[toy.OTTO].location == toy.SQUARE


def test_causes_must_point_to_earlier_events():
    session = toy.build_toy()
    with pytest.raises(CommitError):
        session.commit([draft(causes=[session.state.seq + 1])])
    session.commit([draft(causes=[1])])


def test_observe_sees_state_at_each_event():
    session = toy.build_toy()
    result = session.commit(
        [
            draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE)),
            draft(fx.MoveEntity(entity=toy.ANNA, to=toy.TAVERN)),
        ],
        observe=lambda event, state: state.entities[toy.ANNA].location,
    )
    assert result.observed == [toy.SQUARE, toy.TAVERN]


def test_events_round_trip_through_the_store():
    session = toy.build_toy()
    session.commit(
        [
            draft(
                fx.Utter(
                    speaker=toy.ANNA,
                    text="The mayor is hoarding grain.",
                    claims=[fx.Claim(subject=toy.OTTO, predicate="hoards", value="grain")],
                ),
                actor=toy.ANNA,
                kind="utterance",
                location=toy.BAKERY,
                loud=True,
            )
        ]
    )
    stored = session.store.events(session.branch_id, actor=toy.ANNA)
    assert len(stored) == 1
    assert stored[0].effects[0].claims[0].predicate == "hoards"
    assert stored[0].loud is True
    assert stored[0].location == toy.BAKERY


def _random_drafts(rng: random.Random, state: WorldState, count: int) -> list[EventDraft]:
    people = [toy.ANNA, toy.OTTO, toy.LENA]
    places = [toy.SQUARE, toy.BAKERY, toy.BACK_ROOM, toy.TOWN_HALL, toy.TAVERN, toy.FARM]
    drafts = []
    for index in range(count):
        choice = rng.randrange(6)
        if choice == 0:
            effect = fx.MoveEntity(entity=rng.choice(people), to=rng.choice(places))
        elif choice == 1:
            effect = fx.ChangeQuantity(holder=rng.choice(people), item=toy.COIN, delta=rng.randint(1, 5))
        elif choice == 2:
            effect = fx.AdvanceTime(minutes=rng.randint(1, 600))
        elif choice == 3:
            first, second = rng.sample(people, 2)
            effect = fx.SetRelation(source=first, dest=second, value=rng.randint(-100, 100))
        elif choice == 4:
            effect = fx.AssertFact(fact=Fact(id=f"fact:f{index}", text=f"Fact {index}"))
        else:
            effect = fx.SetAttr(entity=rng.choice(people), key="mood", value=rng.choice(["calm", "angry"]))
        drafts.append(draft(effect))
    return drafts


@pytest.mark.parametrize("seed", range(8))
def test_fold_from_snapshot_and_tail_equals_fold_from_zero(seed):
    rng = random.Random(seed)
    session = toy.build_toy(snapshot_every=7)
    for _ in range(6):
        session.commit(_random_drafts(rng, session.state, rng.randint(1, 9)))
    store, branch = session.store, session.branch_id

    from_zero = store.state_at(branch, use_snapshots=False)
    from_snapshot = store.state_at(branch)
    refolded = fold(store.initial_state(branch), store.events(branch))

    assert store.query("SELECT COUNT(*) AS n FROM snapshots")[0]["n"] > 0
    assert from_zero == from_snapshot == refolded == session.state

    middle = session.state.seq // 2
    assert store.state_at(branch, middle) == store.state_at(branch, middle, use_snapshots=False)


def test_reopened_session_has_the_same_state(tmp_path):
    path = str(tmp_path / "world.sqlite")
    session = toy.build_toy(Store(path))
    session.commit([draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE))])
    expected = session.state
    session.store.close()

    reopened = WorldSession(Store(path), session.branch_id)
    assert reopened.state == expected


# -- branches ----------------------------------------------------------------


def test_fork_sees_parent_up_to_fork_point_and_none_after():
    main = toy.build_toy()
    main.commit([draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE))])
    fork_at = main.state.seq
    main.commit([draft(fx.MoveEntity(entity=toy.ANNA, to=toy.TAVERN))])

    child = main.fork(fork_at, "what-if")
    assert child.state.seq == fork_at
    assert child.state.entities[toy.ANNA].location == toy.SQUARE

    child.commit([draft(fx.Kill(entity=toy.OTTO))])
    main.commit([draft(fx.MoveEntity(entity=toy.LENA, to=toy.SQUARE))])

    assert child.state.entities[toy.OTTO].alive is False
    assert child.state.entities[toy.LENA].location == toy.FARM
    assert main.state.entities[toy.OTTO].alive is True
    assert main.state.entities[toy.ANNA].location == toy.TAVERN

    store = main.store
    assert [e.seq for e in store.events(child.branch_id, after=fork_at)] == [fork_at + 1]
    assert store.state_at(main.branch_id) == main.state
    assert store.state_at(child.branch_id) == child.state


def test_fork_of_a_fork_before_the_first_fork_point():
    main = toy.build_toy()
    main.commit([draft(fx.AdvanceTime(minutes=10)) for _ in range(4)])
    child = main.fork(main.state.seq, "a")
    child.commit([draft(fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE))])
    grandchild = child.fork(8, "b")

    assert grandchild.state.seq == 8
    assert grandchild.state.entities[toy.ANNA].location == toy.BAKERY
    assert branches.ancestors(main.store, grandchild.branch_id) == [
        main.branch_id, child.branch_id, grandchild.branch_id,
    ]


def test_cannot_fork_beyond_head():
    main = toy.build_toy()
    with pytest.raises(StoreError):
        main.fork(main.state.seq + 1, "future")


def test_diverging_events_between_siblings():
    main = toy.build_toy()
    split = main.state.seq
    first = main.fork(split, "first")
    second = main.fork(split, "second")
    first.commit([draft(fx.Kill(entity=toy.OTTO))])
    second.commit([draft(fx.Kill(entity=toy.LENA)), draft(fx.AdvanceTime(minutes=5))])

    at, left, right = branches.diverging_events(main.store, first.branch_id, second.branch_id)
    assert at == split
    assert len(left) == 1 and len(right) == 2
    assert [b.name for b in branches.tree(main.store, main.world_id)] == ["main", "first", "second"]
