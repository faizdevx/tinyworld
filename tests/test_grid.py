import asyncio
from datetime import datetime

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft, Intent, Verb
from tinyworld.core.reducers import EffectError, apply_effect
from tinyworld.core.session import WorldSession
from tinyworld.core.state import Entity, Region, WorldState
from tinyworld.core.store import Store
from tinyworld.eval import invariants
from tinyworld.eval.v7_experiments import fixture_session
from tinyworld.fixtures import berlin, lucknow
from tinyworld.genesis import layout
from tinyworld.gm import rules
from tinyworld.gm.perception import perceive
from tinyworld.world import grid, walking


def run(coroutine):
    return asyncio.run(coroutine)


def tiny() -> WorldSession:
    """Two rooms and a street between, hand-painted:

        ##########
        #,,,,#,,,#      A (room, door at 5,4)   B (room, door at 10,4)
        #,,,,#,,,#
        #,,,,#,,,#
        ####+####        street along y=5
        ==========
    """
    store = Store()
    world = store.create_world("tiny", datetime(2000, 1, 1, 8))
    session = WorldSession(store, store.create_branch(world, "main"))
    places = [
        Entity(id=f"place:{n}", kind="place", name=n.title(), attrs={})
        for n in ("a", "b", "street", "street2")
    ]
    people = [
        Entity(id="person:ann", kind="person", name="Ann", location="place:a", attrs={"persona": {"summary": "Ann, a neighbour."}, "tier": 0}),
        Entity(id="person:bo", kind="person", name="Bo", location="place:b", attrs={"persona": {"summary": "Bo, a neighbour."}, "tier": 0}),
    ]
    rows = [
        "##########....",
        "#,,,,#,,,,#...",
        "#,,,,#,,,,#...",
        "#,,,,#,,,,#...",
        "####+##+##+...",
        "==============",
    ]
    tiles = [fx.Tile(x=x, y=y, terrain=c) for y, row in enumerate(rows) for x, c in enumerate(row)]
    session.commit([EventDraft(actor="system", visibility="god_only", effects=[
        *[fx.CreateEntity(entity=e) for e in places + people],
        fx.SetTiles(tiles=tiles, regions=[
            Region(place="place:street", x0=0, y0=0, x1=7, y1=31),
            Region(place="place:street2", x0=8, y0=0, x1=31, y1=31),
            Region(place="place:a", x0=0, y0=0, x1=4, y1=4),
            Region(place="place:b", x0=5, y0=0, x1=9, y1=4),
        ]),
        fx.SetPosition(entity="person:ann", x=2, y=2),
        fx.SetPosition(entity="person:bo", x=7, y=2),
    ])])
    return session


# -- terrain and positions ---------------------------------------------------


def test_a_person_stands_in_the_place_that_owns_their_tile():
    s = tiny()
    assert s.state.entities["person:ann"].location == "place:a"
    apply_effect(s.state, fx.SetPosition(entity="person:ann", x=4, y=4))  # the door of A
    assert s.state.entities["person:ann"].location == "place:a"
    apply_effect(s.state, fx.SetPosition(entity="person:ann", x=4, y=5))
    assert s.state.entities["person:ann"].location == "place:street"


def test_nobody_can_stand_in_a_wall_or_off_the_map():
    s = tiny().state
    with pytest.raises(EffectError, match="cannot be walked"):
        apply_effect(s, fx.SetPosition(entity="person:ann", x=0, y=0))
    with pytest.raises(EffectError, match="not been generated"):
        apply_effect(s, fx.SetPosition(entity="person:ann", x=500, y=500))


def test_one_step_cannot_jump_across_the_world():
    s = tiny().state
    apply_effect(s, fx.SetTiles(tiles=[fx.Tile(x=300, y=5, terrain=",")], regions=[Region(place="place:street", x0=300, y0=5, x1=300, y1=5)]))
    with pytest.raises(EffectError, match="too far"):
        apply_effect(s, fx.SetPosition(entity="person:ann", x=300, y=5))


def test_unknown_terrain_is_refused():
    s = tiny().state
    with pytest.raises(EffectError, match="unknown terrain"):
        apply_effect(s, fx.SetTiles(tiles=[fx.Tile(x=1, y=1, terrain="?")]))


def test_terrain_revision_changes_only_when_terrain_does():
    s = tiny().state
    before = s.grid_rev
    apply_effect(s, fx.SetPosition(entity="person:ann", x=2, y=3))
    assert s.grid_rev == before
    apply_effect(s, fx.SetTiles(tiles=[fx.Tile(x=12, y=1, terrain="~")]))
    assert s.grid_rev != before


def test_a_state_with_a_map_round_trips():
    s = tiny().state
    assert WorldState.model_validate_json(s.model_dump_json()).grid_rev == s.grid_rev


# -- paths and senses --------------------------------------------------------


def test_paths_go_through_doors_and_around_walls():
    s = tiny().state
    path = grid.find_path(s, (2, 2), (7, 2))
    assert path[0] == (2, 2) and path[-1] == (7, 2)
    assert (4, 4) in path and (7, 4) in path  # out of A's door, along the street, in at B's
    assert all(grid.passable(s, *t) for t in path)
    assert all(grid.terrain_at(s, *t) != "#" for t in path)


def test_no_path_to_a_wall():
    assert grid.find_path(tiny().state, (2, 2), (0, 0)) is None


def test_a_wall_blocks_sight_and_muffles_sound():
    s = tiny().state
    ann, bo = (2, 2), (7, 2)
    assert not grid.sees(s, ann, bo)  # the wall at x=5 stands between them
    assert grid.sees(s, ann, (3, 3))
    assert not grid.hears(s, ann, bo)  # one wall leaves 8 - 4 = 4 tiles of reach; they are 5 apart
    assert grid.hears(s, ann, bo, loud=True)  # a shout carries through
    assert grid.hears(s, ann, (4, 2))  # no wall, close


def test_the_street_sees_along_itself():
    s = tiny().state
    assert grid.sees(s, (0, 5), (12, 5))
    assert not grid.sees(s, (0, 5), (12, 5), radius=5)


def test_events_are_seen_across_the_street_but_not_through_walls():
    s = tiny()
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetPosition(entity="person:ann", x=4, y=5), fx.SetPosition(entity="person:bo", x=12, y=5)])])
    from tinyworld.core.events import Event

    event = Event(branch_id="b", seq=99, sim_time=s.state.sim_time, kind="action", actor="person:ann",
                  location="place:street", narration="Ann waves.", effects=[], visibility="witnessed")
    seen = {o.observer for o in perceive(event, s.state)}
    assert "person:bo" in seen
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.SetPosition(entity="person:bo", x=7, y=2)])])
    event = event.model_copy(update={"location": "place:street"})
    seen = {o.observer for o in perceive(event, s.state)}
    assert "person:bo" not in seen


# -- walking -----------------------------------------------------------------


def test_a_move_is_a_walk_in_legs_that_others_can_interrupt():
    s = tiny()
    intent = Intent(agent="person:ann", verb=Verb.MOVE, target="place:b", text="go to B")
    verdict = rules.check(s.state, intent)
    assert verdict.status == "resolved" and "arrives" in verdict.outcome.narration
    assert any(isinstance(e, fx.SetPosition) for e in verdict.outcome.effects)
    assert verdict.outcome.minutes >= 1
    s.commit([EventDraft(actor="person:ann", effects=verdict.outcome.effects, narration="walks")])
    # Short walk: done in one leg, route cleared, standing in B.
    assert s.state.entities["person:ann"].location == "place:b"
    assert walking.route_of(s.state.entities["person:ann"]) is None


def test_a_long_walk_takes_several_legs_and_arrives():
    s = fixture_session(berlin)
    ann = "person:anna_keller"
    state = s.state
    target = "place:vogel_farm"
    legs, minutes = 0, 0
    while state.entities[ann].location != target and legs < 40:
        v = rules.check(state, Intent(agent=ann, verb=Verb.MOVE, target=target, args={"continue": legs > 0}))
        assert v.status == "resolved", v.reason
        s.commit([EventDraft(actor=ann, effects=v.outcome.effects, narration=v.outcome.narration)])
        state = s.state
        minutes += v.outcome.minutes
        legs += 1
    assert state.entities[ann].location == target
    assert legs > 3 and minutes >= 20
    assert walking.route_of(state.entities[ann]) is None


def test_doing_something_else_ends_the_walk():
    from tinyworld.gm.master import outcome_draft
    from tinyworld.core.events import Outcome

    s = fixture_session(berlin)
    ann = "person:anna_keller"
    v = rules.check(s.state, Intent(agent=ann, verb=Verb.MOVE, target="place:vogel_farm"))
    s.commit([EventDraft(actor=ann, effects=v.outcome.effects)])
    assert walking.route_of(s.state.entities[ann]) == "place:vogel_farm"
    speak = Intent(agent=ann, verb=Verb.WAIT, args={"minutes": 5})
    outcome = rules.check(s.state, speak).outcome
    draft = outcome_draft(s.state, outcome)
    s.commit([draft])
    assert walking.route_of(s.state.entities[ann]) is None


def test_two_people_in_a_street_can_talk_if_they_are_close():
    s = tiny()
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetPosition(entity="person:ann", x=4, y=5), fx.SetPosition(entity="person:bo", x=7, y=5)])])
    ann, bo = s.state.entities["person:ann"], s.state.entities["person:bo"]
    assert grid.can_talk(s.state, ann, bo)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.SetPosition(entity="person:bo", x=13, y=5)])])
    assert not grid.can_talk(s.state, s.state.entities["person:ann"], s.state.entities["person:bo"])


# -- the layout --------------------------------------------------------------


@pytest.mark.parametrize("module", [berlin, lucknow])
def test_a_fixture_world_is_laid_out_and_every_place_is_reachable(module):
    s = fixture_session(module)
    state = s.state
    assert state.grid
    places = [p for p in state.entities.values() if p.kind == "place"]
    hub = places[0].id
    assert [p.name for p in places if state.path(hub, p.id) is None] == []
    for person in state.people():
        spot = grid.position_of(person)
        assert spot is not None and grid.passable(state, *spot)
        assert grid.place_at(state, *spot) == person.location


@pytest.mark.parametrize("module", [berlin, lucknow])
def test_the_derived_place_graph_keeps_every_link_of_the_bible(module):
    plain = fixture_session(module, laid_out=False).state
    laid = fixture_session(module).state
    for key in plain.edges:
        a, b = key.split("|")
        assert laid.path(a, b) is not None, key


def test_the_layout_is_the_same_every_time():
    a = [d.model_dump_json() for d in layout.layout(fixture_session(lucknow, laid_out=False).state)]
    b = [d.model_dump_json() for d in layout.layout(fixture_session(lucknow, laid_out=False).state)]
    assert a == b


def test_buildings_do_not_overlap_and_doors_face_a_road():
    s = fixture_session(lucknow).state
    plots, rooms, _ = layout.plan(s)
    layout._normalise(plots)
    names = sorted(plots)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if plots[a].room_of == b or plots[b].room_of == a or (plots[a].room_of and plots[a].room_of == plots[b].room_of):
                continue
            ax0, ay0, ax1, ay1 = plots[a].rect()
            bx0, by0, bx1, by1 = plots[b].rect()
            assert not (ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1), (a, b)
    for place in s.entities:
        if s.entities[place].kind == "place" and not s.entities[place].attrs.get("enclosed") and place in plots:
            if not plots[place].open and plots[place].room_of is None:
                doors = grid.doors(s, place)
                assert doors, place


def test_a_laid_out_world_passes_the_invariants_through_a_long_asynchronous_run():
    from tinyworld.eval.v7_experiments import town_for
    from tinyworld.sim.clock import AsyncSimulation

    s = fixture_session(berlin)
    s.debug = True
    town = town_for(s, chaos=0.0, petitioning=False, paper=False)
    clocks = AsyncSimulation(town.sim, town.entropy)
    run(clocks.run_for(10 * 60))
    assert invariants.check_log(s.store, s.branch_id) == []
    walked = [e for e in s.store.events(s.branch_id) if any(isinstance(x, fx.SetPosition) for x in e.effects)]
    assert len(walked) > 20


def test_two_people_who_see_each_other_in_a_street_start_talking():
    from tinyworld.eval.v7_experiments import town_for
    from tinyworld.sim.clock import AsyncSimulation

    s = tiny()
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetPosition(entity="person:ann", x=4, y=5), fx.SetPosition(entity="person:bo", x=8, y=5)])])
    town = town_for(s, chaos=0.0, petitioning=False, paper=False)

    def act(request):
        me = request.context.agent
        other = "person:bo" if me == "person:ann" else "person:ann"
        if "In view" in request.user or f"[{other}]" in request.user:
            return {"verb": "speak", "text": "greet", "say": {"text": "Good morning!", "to": [other]}}
        return {"verb": "wait", "text": "wait", "args": {"minutes": 10}}

    town.sim.llm.client.on("agent.act", act)
    clocks = AsyncSimulation(town.sim, town.entropy)
    run(clocks.step())
    spoken = [e for e in s.store.events(s.branch_id) if e.kind == "utterance"]
    assert spoken, "nobody spoke"
    assert spoken[0].location in ("place:street", "place:street2")
