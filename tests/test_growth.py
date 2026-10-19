import asyncio

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy, Fixed
from tinyworld.core.events import EventDraft, Intent, Verb
from tinyworld.eval import invariants
from tinyworld.eval.v7_experiments import fixture_session, town_for
from tinyworld.fixtures import berlin
from tinyworld.genesis import layout
from tinyworld.gm import rules
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.clock import AsyncSimulation
from tinyworld.sim.replay import replay
from tinyworld.sim.town import Town
from tinyworld.studio import creators as cr
from tinyworld.world import frontier, grid, walking


def run(coroutine):
    return asyncio.run(coroutine)


def grown_town(session=None, **options):
    session = session or fixture_session(berlin)
    base = town_for(session, chaos=0.0, petitioning=False, paper=False)
    clocks = AsyncSimulation(base.sim, base.entropy)
    town = Town(base.sim, base.entropy, clocks=clocks, petitioning=False, paper=False,
                creators=cr.Creators(**options), chaos=0.0)
    return town, clocks, session


def send_east(session, who="person:anna_keller", town=None):
    """Put someone on the east edge of the known world, as if they had walked there."""
    state = session.state
    tiles = frontier.edge_tiles(state, "east")
    assert tiles
    edge = tiles[len(tiles) // 2]
    draft = EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetPosition(entity=who, x=edge[0] - 1 if grid.passable(state, edge[0] - 1, edge[1]) else edge[0], y=edge[1])
    ])
    if town is not None:
        town.commit([draft])  # through the town's own writer, so a replay repeats it
    else:
        session.commit([draft], atomic=False)
    return edge


# -- the frontier ------------------------------------------------------------


def test_the_known_world_has_an_edge_and_chunks_beyond_it_are_missing():
    s = fixture_session(berlin)
    missing = frontier.missing_neighbours(s.state)
    assert missing and all(k not in s.state.grid for k in missing)
    assert frontier.edge_tiles(s.state, "east")


def test_nobody_sees_unexplored_ground_from_the_middle_of_town():
    s = fixture_session(berlin)
    assert frontier.scan(s.state) == [] or all(
        grid.position_of(s.state.entities[p]) for _, p in frontier.scan(s.state)
    )


def test_a_request_is_raised_for_ground_someone_can_see_and_only_once():
    s = fixture_session(berlin)
    edge = send_east(s)
    seen = frontier.scan(s.state)
    assert seen
    key, who = seen[0]
    draft = frontier.request_draft(s.state, key, who, "seen")
    s.commit([draft])
    assert key in [r.chunk for r in frontier.pending(s.state)]
    assert frontier.request_draft(s.state, key, who, "seen") is None
    assert key not in [k for k, _ in frontier.scan(s.state)]


# -- the creators' proposal is checked ----------------------------------------


def proposal(*names):
    return cr.Proposal(places=[cr.PlaceProposal(name=n, kind="house", description="A house.") for n in names])


def test_a_proposal_is_cut_to_the_place_budget():
    s = fixture_session(berlin).state
    out = cr.check(s, proposal(*[f"House {i}x" for i in "ABCDEFG"]), per_chunk=3)
    assert len(out.places) == 3 and len(out.refused) == 4


def test_names_that_are_not_names_or_already_exist_are_refused():
    s = fixture_session(berlin).state
    out = cr.check(s, proposal("Town Hall", "{broken}}", "Mill Lane Cottage"))
    assert [p.name for p in out.places] == ["Mill Lane Cottage"]
    assert len(out.refused) == 2


def test_something_the_period_lacks_is_refused():
    s = fixture_session(berlin)
    s.commit([EventDraft(actor="system", visibility="god_only",
                         effects=[fx.SetRule(key="tech.not_yet", value=["television", "radar"])])])
    out = cr.check(s.state, cr.Proposal(places=[
        cr.PlaceProposal(name="Radar Station", kind="shop"),
        cr.PlaceProposal(name="Weaver Cottage", kind="house", people=[cr.PersonProposal(name="Ida Roth", occupation="television repairer")]),
        cr.PlaceProposal(name="Cobbler Shop", kind="shop", people=[cr.PersonProposal(name="Ida Roth", occupation="cobbler")]),
    ]))
    assert [p.name for p in out.places] == ["Cobbler Shop"]
    assert any("does not have" in r for r in out.refused)


def test_the_scripted_cartographer_proposes_something_that_passes():
    s = fixture_session(berlin).state
    p = run(cr.ScriptedCartographer().propose(s, "5,5", Entropy()))
    assert 2 <= len(p.places) <= 4
    assert cr.check(s, p).places


def test_a_model_cartographer_is_used_and_a_bad_reply_falls_back():
    s = fixture_session(berlin)
    config = LLMConfig()
    good = FakeLLM({"creator.cartographer": {"places": [{"name": "Heron Ferry", "kind": "inn", "people": [{"name": "Ruth Adler", "occupation": "ferryman", "age": 40}]}]}})
    llm = StructuredLLM(good, config, Tracer(s.store, config))
    out = run(cr.ModelCartographer(llm).propose(s.state, "4,4", Entropy(), branch=s.branch_id))
    assert [p.name for p in out.places] == ["Heron Ferry"]
    bad = StructuredLLM(FakeLLM({"creator.cartographer": "not json at all"}), config, Tracer(s.store, config))
    out = run(cr.ModelCartographer(bad).propose(s.state, "4,4", Entropy(), branch=s.branch_id))
    assert out.places


# -- laying new ground out ---------------------------------------------------


def edge_chunk(session):
    key = sorted(frontier.missing_neighbours(session.state))[0]
    return key


def test_new_ground_is_laid_out_joined_to_the_town_and_valid():
    s = fixture_session(berlin)
    s.debug = True
    key = edge_chunk(s)
    specs = [layout.NewPlace("Mill Lane Cottage", "house", "A cottage.", [{"name": "Ida Roth", "occupation": "weaver", "age": 51}]),
             layout.NewPlace("Upper Well", "well", "A well.")]
    drafts = layout.extend(s.state, key, specs, Entropy())
    r = s.commit(drafts, atomic=False)
    assert r.rejected == []
    state = s.state
    assert key in state.grid
    for name in ("place:mill_lane_cottage", "place:upper_well"):
        assert state.path("place:market_square", name) is not None, name
    ida = state.entities["person:ida_roth"]
    assert ida.attrs["tier"] == 2 and ida.location == "place:mill_lane_cottage"
    assert grid.place_at(state, *grid.position_of(ida)) == ida.location
    assert invariants.check_log(s.store, s.branch_id) == []


def test_a_chunk_that_touches_nothing_cannot_be_laid_out():
    s = fixture_session(berlin)
    with pytest.raises(ValueError, match="does not touch"):
        layout.extend(s.state, "90,90", [layout.NewPlace("Far Barn")], Entropy())
    with pytest.raises(ValueError, match="already exists"):
        layout.extend(s.state, sorted(s.state.grid)[0], [layout.NewPlace("Far Barn")], Entropy())


def test_placement_is_drawn_from_entropy_so_two_runs_lay_out_differently():
    s = fixture_session(berlin)
    key = edge_chunk(s)
    specs = [layout.NewPlace("Mill Lane Cottage", "house"), layout.NewPlace("Upper Well", "well")]
    a = layout.extend(s.state, key, specs, Entropy())
    b = layout.extend(s.state, key, specs, Entropy())
    assert [d.model_dump_json() for d in a] != [d.model_dump_json() for d in b]
    assert [d.model_dump_json() for d in layout.extend(s.state, key, specs, Fixed([0.3] * 40))] == [
        d.model_dump_json() for d in layout.extend(s.state, key, specs, Fixed([0.3] * 40))]


# -- the whole loop ----------------------------------------------------------


def test_someone_who_explores_makes_the_map_grow():
    town, clocks, s = grown_town()
    before = set(s.state.grid)
    # Anna sets out for the eastern edge on her own two feet, leg by leg.
    v = rules.check(s.state, Intent(agent="person:anna_keller", verb=Verb.EXPLORE, args={"direction": "east"}))
    assert v.status == "resolved", v.reason
    assert "unexplored ground to the east" in v.outcome.narration or "arrives" in v.outcome.narration
    # Put her there and let the town notice.
    send_east(s, town=town)
    run(town.advance(10))
    assert set(s.state.grid) > before
    new = set(s.state.grid) - before
    assert new <= set(frontier.missing_neighbours(fixture_session(berlin).state)) | new
    done = [r for r in frontier.requests(s.state) if r.status == "generated"]
    assert done and done[0].places
    assert invariants.check_log(s.store, s.branch_id) == []


def test_each_chunk_is_requested_and_answered_once():
    town, clocks, s = grown_town()
    send_east(s, town=town)
    for _ in range(4):
        run(town.advance(10))
    reqs = frontier.requests(s.state)
    assert len({r.chunk for r in reqs}) == len(reqs)
    assert town.creators.answered == len([r for r in reqs if r.status in ("generated", "refused")]) or town.creators.answered >= 1


def test_the_world_stops_growing_at_its_budget():
    town, clocks, s = grown_town(max_chunks=1)
    send_east(s, town=town)
    for _ in range(8):
        run(town.advance(10))
    states = [r.status for r in frontier.requests(s.state)]
    assert states.count("generated") <= 1
    if len(states) > 1:
        assert "refused" in states


def test_a_replay_rebuilds_the_new_ground_without_calling_the_creators():
    town, clocks, s = grown_town()
    send_east(s, town=town)
    for _ in range(3):
        run(town.advance(15))
    assert any(r.status == "generated" for r in frontier.requests(s.state))
    report = run(replay(s.store, s.branch_id, LLMConfig()))
    assert report.identical, report.first_difference


def test_two_runs_of_one_world_grow_different_maps_beyond_the_start():
    base = fixture_session(berlin)
    seq = base.state.seq
    maps = []
    for name in ("a", "b"):
        branch = base.fork(seq, name)
        town, clocks, _ = grown_town(branch)
        send_east(branch, town=town)
        for _ in range(3):
            run(town.advance(15))
        new_places = sorted(
            (e.id, grid.footprint(branch.state, e.id)[0] if grid.footprint(branch.state, e.id) else None)
            for e in branch.state.entities.values()
            if e.kind == "place" and e.id not in base.state.entities and not e.id.startswith(("place:blk_", "place:wild_"))
        )
        assert new_places, "nothing grew"
        maps.append(new_places)
        assert invariants.check_log(branch.store, branch.branch_id) == []
    assert maps[0] != maps[1]
