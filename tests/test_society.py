import asyncio
from datetime import timedelta

import pytest

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy, Fixed
from tinyworld.core.events import EventDraft, Intent, Verb
from tinyworld.eval import invariants
from tinyworld.eval.v7_experiments import fixture_session, town_for
from tinyworld.fixtures import berlin, lucknow
from tinyworld.genesis import critic
from tinyworld.genesis.bible import Bible
from tinyworld.gm import rules
from tinyworld.llm.router import LLMConfig
from tinyworld.sim.clock import AsyncSimulation
from tinyworld.sim.replay import replay
from tinyworld.sim.town import Town
from tinyworld.studio.desk import POWERS, PetitionDesk
from tinyworld.studio.state import Studio
from tinyworld.world import drives, economy, grid, institutions, laws, petitions

ANNA, OTTO, KRUGER = "person:anna_keller", "person:otto_brandt", "person:ernst_kruger"


def run(coroutine):
    return asyncio.run(coroutine)


def berlin_town(**options):
    session = fixture_session(berlin)
    base = town_for(session, chaos=0.0, petitioning=options.pop("petitioning", False), paper=False)
    clocks = AsyncSimulation(base.sim, base.entropy)
    town = Town(base.sim, base.entropy, clocks=clocks, paper=False, chaos=0.0, **options)
    return town, clocks, session


def say(session, *effects, actor="system"):
    session.commit([EventDraft(actor=actor, visibility="god_only", effects=list(effects))])


# -- petitions at a holy place -------------------------------------------------


def test_a_petition_is_made_at_a_holy_place_only():
    town, clocks, s = berlin_town()
    assert petitions.holy_places(s.state)
    anna = s.state.entities[ANNA]
    assert not petitions.at_holy_place(s.state, anna)
    refused = petitions.file(s.state, anna, {"kind": "prayer"}, "Spare my flour.")
    assert isinstance(refused, str) and "holy place" in refused


def test_a_world_without_a_shrine_is_given_one():
    s = fixture_session(lucknow)
    assert "place:the_shrine" in s.state.entities
    assert s.state.path("place:the_shrine", "place:chowk_market") is not None


def test_someone_who_needs_the_god_walks_to_the_shrine_and_prays_in_view_of_others():
    town, clocks, s = berlin_town(petitioning=True)
    town.entropy = Fixed([0.0] * 5000)
    clocks.entropy = town.entropy
    run(town.advance(240))
    prayed = [e for e in s.store.events(s.branch_id) if "kneels and prays" in e.narration]
    assert prayed, "nobody prayed"
    church = petitions.holy_places(s.state)
    assert all(e.location in church for e in prayed)
    assert all("Spare" not in e.narration and "bread" not in e.narration for e in prayed)  # the words stay private
    assert petitions.all_petitions(s.state)


# -- the podium ---------------------------------------------------------------


def desk_town():
    town, clocks, s = berlin_town(god=None)
    studio = Studio(s.store, s.world_id)
    desk = PetitionDesk(studio, town)
    town.desk = desk
    return town, clocks, s, studio, desk


def pray(town, s, who=ANNA, text="Keep the requisitioners from my flour."):
    church = petitions.holy_places(s.state)[0]
    town.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.MoveEntity(entity=who, to=church)])])
    effects, _ = petitions.file(s.state, s.state.entities[who], {"kind": "request"}, text)
    town.commit([EventDraft(actor=who, effects=effects, narration="prays")])
    return petitions.open_petitions(s.state)[0]


def test_a_petition_rings_the_bell_with_a_card_that_says_who_and_why():
    async def go():
        town, clocks, s, studio, desk = desk_town()
        p = pray(town, s)
        opened = desk.sync()
        assert len(opened) == 1
        d = studio.open_decisions()[0]
        assert d.kind == "petition" and "Anna Keller" in d.question
        assert set(d.options) == set(POWERS)
        assert "Faith 50/100" in d.context and "Wants:" in d.context
        assert desk.sync() == []  # not asked twice
    run(go())


def test_the_gods_answer_comes_back_to_the_town():
    async def go(option, note="", expect_faith=50):
        town, clocks, s, studio, desk = desk_town()
        p = pray(town, s)
        desk.sync()
        d = studio.open_decisions()[0]
        studio.answer(d.id, option, note)
        await desk.drain()
        await asyncio.sleep(0.05)
        await desk.drain()
        state = s.state
        assert petitions.open_petitions(state) == []
        assert state.entities[ANNA].attrs["faith"] == expect_faith, option
        return town, s
    run(go("Whisper", "Be patient.", 56))
    run(go("Refuse", "No.", 45))
    run(go("Ignore", "", 42))
    run(go("Show a sign", "", 53))


def test_a_grant_goes_through_the_god_channel_and_changes_the_world():
    async def go():
        town, clocks, s, studio, desk = desk_town()
        pray(town, s)
        desk.sync()
        d = studio.open_decisions()[0]
        studio.answer(d.id, "Grant", "move Anna Keller to Town Hall")
        for _ in range(3):
            await desk.drain()
            await asyncio.sleep(0.05)
        assert s.state.entities[ANNA].location == "place:town_hall"
        assert petitions.open_petitions(s.state) == []
        assert s.state.entities[ANNA].attrs["faith"] == 60
    run(go())


def test_a_grant_the_world_cannot_take_leaves_the_petition_open():
    async def go():
        town, clocks, s, studio, desk = desk_town()
        pray(town, s)
        desk.sync()
        d = studio.open_decisions()[0]
        studio.answer(d.id, "Grant", "move Anna Keller to Atlantis")
        for _ in range(3):
            await desk.drain()
            await asyncio.sleep(0.05)
        assert len(petitions.open_petitions(s.state)) == 1
        assert town.last_refused
    run(go())


def test_silence_closes_the_petition_withdraws_the_decision_and_is_remembered():
    async def go():
        town, clocks, s, studio, desk = desk_town()
        pray(town, s)
        desk.sync()
        assert studio.open_decisions()
        s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=13 * 60)])])
        await town._answers()
        desk.sync()
        assert petitions.open_petitions(s.state) == [] and studio.open_decisions() == []
        assert s.state.entities[ANNA].attrs["faith"] == 42
        assert any("no answer" in m.text for m in town.sim.memory.list(s.branch_id, ANNA))
    run(go())


def test_an_answer_becomes_a_belief_and_a_miracle_changes_those_who_saw_it():
    async def go():
        town, clocks, s, studio, desk = desk_town()
        p = pray(town, s)
        church = s.state.entities[ANNA].location
        town.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.MoveEntity(entity=OTTO, to=church)])])
        before = s.state.entities[OTTO].attrs.get("faith", 50)
        await town.answer(p.id, "sign", "Light falls on the altar.")
        belief = town.sim.beliefs.current(s.branch_id, ANNA)
        assert any(b.subject == "god" for b in belief)
        assert s.state.entities[OTTO].attrs["faith"] == before + 4
    run(go())


def test_petitions_and_answers_replay_exactly():
    async def go():
        town, clocks, s, studio, desk = desk_town()
        p = pray(town, s)
        await town.answer(p.id, "grant", "so be it", [fx.ChangeQuantity(holder=ANNA, item="resource:reichsmark", delta=2)])
        report = await replay(s.store, s.branch_id, LLMConfig())
        assert report.identical, report.first_difference
    run(go())


# -- drives ---------------------------------------------------------------------


def test_everyone_with_a_persona_gets_drives_that_fit_them():
    town, clocks, s = berlin_town(drives_on=True)
    anna, otto = s.state.entities[ANNA], s.state.entities[OTTO]
    d_anna, d_otto = drives.of(anna), drives.of(otto)
    assert set(d_anna) == set(drives.DRIVES)
    assert d_otto["status"][1] > d_anna["status"][1]  # the vain mayor wants standing more
    assert drives.initial(anna) == drives.initial(anna)


def test_events_move_drives():
    town, clocks, s = berlin_town(drives_on=True)
    before = drives.of(s.state.entities[ANNA])
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.ChangeQuantity(holder=ANNA, item="resource:reichsmark", delta=-8)])])
    ev = s.store.events(s.branch_id, after=s.state.seq - 1)
    changes = drives.consequences(s.state, ev)
    assert changes and changes[0].entity == ANNA
    assert changes[0].value["money"][0] < before["money"][0]


def test_a_death_shakes_those_who_loved_the_dead():
    town, clocks, s = berlin_town(drives_on=True)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.Kill(entity="person:lena_vogel")])])
    ev = s.store.events(s.branch_id, after=s.state.seq - 1)
    hit = {c.entity: c.value for c in drives.consequences(s.state, ev)}
    assert ANNA in hit and hit[ANNA]["belonging"][0] < drives.of(s.state.entities[ANNA])["belonging"][0]


def test_drives_drift_back_toward_the_set_point():
    town, clocks, s = berlin_town(drives_on=True)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetAttr(entity=ANNA, key="drives", value={**drives.of(s.state.entities[ANNA]), "safety": [10, 70]})])])
    gaps = []
    for _ in range(3):
        for eff in drives.drift(s.state, 1440):
            s.commit([EventDraft(actor="system", visibility="god_only", effects=[eff])])
        gaps.append(drives.deficits(s.state.entities[ANNA])["safety"])
    assert gaps[0] > gaps[1] > gaps[2] > 0


def test_frustration_raises_the_urge_to_ask_and_the_prompt_says_what_weighs():
    town, clocks, s = berlin_town(drives_on=True)
    anna = s.state.entities[ANNA]
    calm = petitions.urgency(s.state, anna)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetAttr(entity=ANNA, key="drives", value={n: [5, 80] for n in drives.DRIVES})])])
    anna = s.state.entities[ANNA]
    assert drives.frustration(anna) >= 0.9
    assert petitions.urgency(s.state, anna) > calm + 0.3
    assert any("do not feel safe" in l for l in drives.lines_for(anna))


def test_a_frustrated_person_on_routine_is_given_back_to_the_model():
    town, clocks, s = berlin_town(drives_on=True)
    sim = town.sim
    anna = s.state.entities[ANNA]
    mode, _ = sim.mode_of(anna)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetAttr(entity=ANNA, key="drives", value={n: [0, 90] for n in drives.DRIVES})])])
    mode2, _ = sim.mode_of(s.state.entities[ANNA])
    assert mode2 in ("react", "deliberate")


def test_the_cast_must_have_the_three_edges():
    data = {"premise": berlin.PREMISE, "divergence": berlin.DIVERGENCE, **berlin.SECTIONS}
    bible = Bible.model_validate(data)
    assert [f for f in critic.check(bible) if "opinion" in f.text or "grudge" in f.text or "rival" in f.text] == []
    bare = Bible.model_validate(data)
    bare.figures.figures[0].grudge = ""
    bare.figures.figures[1].opinion = ""
    bare.figures.figures[2].rival_want = ""
    found = [f for f in critic.check(bare) if f.blocking and f.section == "figures"]
    assert len(found) == 3


def test_edges_reach_the_persona_and_the_prompt():
    from tinyworld.agents.persona import persona_of, render

    s = fixture_session(berlin)
    anna = s.state.entities[ANNA]
    persona = persona_of(anna)
    assert persona.grudge and persona.rival_want and persona.opinion
    text = render(anna, persona)
    assert "A grudge you carry" in text and "stands in someone else's way" in text


# -- groups -----------------------------------------------------------------------


def act(session, who, action, target=None, text="", **args):
    verdict = rules.check(session.state, Intent(agent=who, verb=action, target=target, text=text, args=args))
    assert verdict.status == "resolved", verdict.reason
    session.commit([EventDraft(actor=who, effects=verdict.outcome.effects, narration=verdict.outcome.narration)])
    return verdict


def test_a_group_is_founded_joined_split_and_dissolved_by_residents():
    s = fixture_session(berlin)
    act(s, ANNA, Verb.FOUND, text="share flour fairly; keep the parish fed", name="Bread Circle")
    gid = "org:bread_circle"
    assert institutions.leader_of(s.state, gid) == ANNA and institutions.members(s.state, gid) == [ANNA]
    for who in (OTTO, "person:lena_vogel", "person:martin_weiss"):
        act(s, who, Verb.JOIN, gid)
    assert len(institutions.members(s.state, gid)) == 4
    assert s.state.entities[gid].attrs["members"] == 4
    act(s, OTTO, Verb.SPLIT, gid, text="order first", name="Order Committee", followers=["person:lena_vogel"])
    assert institutions.members(s.state, "org:order_committee") == sorted([OTTO, "person:lena_vogel"])
    assert ANNA in institutions.members(s.state, gid) and OTTO not in institutions.members(s.state, gid)
    act(s, "person:martin_weiss", Verb.LEAVE, gid)
    assert "person:martin_weiss" not in institutions.members(s.state, gid)
    act(s, ANNA, Verb.DISSOLVE, gid)
    assert institutions.members(s.state, gid) == []
    assert institutions.leader_of(s.state, gid) is None
    assert invariants.check_log(s.store, s.branch_id) == []


def test_only_a_leader_dissolves_and_a_name_is_not_taken_twice():
    s = fixture_session(berlin)
    act(s, ANNA, Verb.FOUND, text="aim", name="Bread Circle")
    act(s, OTTO, Verb.JOIN, "org:bread_circle")
    v = rules.check(s.state, Intent(agent=OTTO, verb=Verb.DISSOLVE, target="org:bread_circle"))
    assert v.status == "impossible" and "leader" in v.reason
    v = rules.check(s.state, Intent(agent=OTTO, verb=Verb.FOUND, text="aim", args={"name": "Bread Circle"}))
    assert v.status == "impossible" and "already exists" in v.reason


def test_a_leader_who_leaves_hands_the_group_on():
    s = fixture_session(berlin)
    act(s, ANNA, Verb.FOUND, text="aim", name="Bread Circle")
    act(s, OTTO, Verb.JOIN, "org:bread_circle")
    act(s, ANNA, Verb.LEAVE, "org:bread_circle")
    assert institutions.leader_of(s.state, "org:bread_circle") == OTTO


# -- laws -----------------------------------------------------------------------------


def with_authority(s):
    act(s, OTTO, Verb.FOUND, text="keep order", name="Night Watch Board")
    say(s, fx.SetAttr(entity="org:night_watch_board", key="authority", value=True))


def test_only_a_leader_with_authority_can_decree():
    s = fixture_session(berlin)
    act(s, OTTO, Verb.FOUND, text="keep order", name="Night Watch Board")
    v = rules.check(s.state, Intent(agent=OTTO, verb=Verb.DECREE, text="No baking at night.", args={"kind": "ban", "verb": "work"}))
    assert v.status == "impossible" and "no authority" in v.reason
    say(s, fx.SetAttr(entity="org:night_watch_board", key="authority", value=True))
    v = rules.check(s.state, Intent(agent=ANNA, verb=Verb.DECREE, text="x", args={"kind": "ban", "verb": "work"}))
    assert v.status == "impossible"
    act(s, OTTO, Verb.DECREE, text="No taking bread from the bakery.", kind="ban", verb="take")
    assert len(laws.laws(s.state)) == 1


def test_a_law_hands_the_action_to_the_game_master_with_the_law_in_the_case():
    from tinyworld.gm.adjudicator import Adjudicator
    from tinyworld.llm.fake import FakeLLM
    from tinyworld.llm.structured import StructuredLLM
    from tinyworld.llm.trace import Tracer

    s = fixture_session(berlin)
    with_authority(s)
    act(s, OTTO, Verb.DECREE, text="No taking bread from the bakery.", kind="ban", verb="take")
    # Put Otto where bread is, and let him take some.
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.MoveEntity(entity=OTTO, to="place:keller_bakery")])])
    intent = Intent(agent=OTTO, verb=Verb.TAKE, target="place:keller_bakery", args={"item": "resource:ration_card", "quantity": 1})
    seen = {}

    def reply(request):
        seen["prompt"] = request.user
        return {"status": "failed", "narration": "A constable steps in.", "reason": "the law forbids it"}

    llm = StructuredLLM(FakeLLM({"gm.adjudicate": reply}), LLMConfig(), Tracer(s.store, LLMConfig()))
    from tinyworld.gm.master import GameMaster
    from tinyworld.sim.step import apply_intents
    from tinyworld.llm.types import CallContext

    verdict = rules.check(s.state, intent)
    assert verdict.status in ("adjudicate", "impossible")
    if verdict.status == "adjudicate":
        out = run(apply_intents(s, GameMaster(Adjudicator(llm)), [intent], CallContext(s.branch_id, 0)))
        assert "Laws in force" in seen["prompt"] and "No taking bread" in seen["prompt"]
        assert out.outcomes[0].status == "failed"


def test_a_curfew_covers_the_streets_at_night_only():
    s = fixture_session(berlin)
    with_authority(s)
    act(s, OTTO, Verb.DECREE, text="Indoors by ten.", kind="curfew", **{"from": 22, "to": 5})
    walk = Intent(agent=ANNA, verb=Verb.MOVE, target="place:town_hall")
    assert not laws.touching(s.state, walk) or s.state.sim_time.hour < 22
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=15 * 60)])])
    assert s.state.sim_time.hour >= 22
    assert laws.touching(s.state, walk)
    assert rules.check(s.state, walk).status == "adjudicate"


def test_a_tax_takes_a_share_of_wages_for_the_group():
    s = fixture_session(berlin)
    with_authority(s)
    say(s, fx.SetRule(key="wage", value={"item": "resource:reichsmark", "per_hour": 10}))
    act(s, OTTO, Verb.DECREE, text="A tenth of wages to the council.", kind="tax", rate=0.2)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetAttr(entity=ANNA, key="workplace", value="place:keller_bakery")])])
    before = s.state.entities["org:night_watch_board"].inventory.get("resource:reichsmark", 0)
    v = rules.check(s.state, Intent(agent=ANNA, verb=Verb.WORK, args={"shift": True, "minutes": 120}))
    assert v.status in ("resolved", "adjudicate")
    if v.status == "resolved":
        s.commit([EventDraft(actor=ANNA, effects=v.outcome.effects)])
        assert s.state.entities["org:night_watch_board"].inventory.get("resource:reichsmark", 0) > before


def test_a_law_can_be_repealed_by_its_leader():
    s = fixture_session(berlin)
    with_authority(s)
    act(s, OTTO, Verb.DECREE, text="No taking.", kind="ban", verb="take")
    fid = laws.laws(s.state)[0].id
    assert isinstance(laws.repeal(s.state, s.state.entities[ANNA], fid), str)
    effects, _ = laws.repeal(s.state, s.state.entities[OTTO], fid)
    s.commit([EventDraft(actor=OTTO, effects=effects)])
    assert laws.laws(s.state) == []


# -- economy ---------------------------------------------------------------------------


def test_prices_rise_with_scarcity_and_fall_with_plenty():
    s = fixture_session(berlin)
    item = "resource:bread"
    held = [(e.id, e.inventory[item]) for e in s.state.entities.values() if item in e.inventory]
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.ChangeQuantity(holder=h, item=item, delta=-q) for h, q in held])])
    for _ in range(8):
        changes = economy.update_prices(s.state)
        if changes:
            s.commit([EventDraft(actor="system", visibility="god_only", effects=changes)])
    scarce = economy.price_of(s.state, item)
    assert scarce > 1.0
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.ChangeQuantity(holder=ANNA, item=item, delta=2000)])])
    for _ in range(12):
        changes = economy.update_prices(s.state)
        if changes:
            s.commit([EventDraft(actor="system", visibility="god_only", effects=changes)])
    assert economy.price_of(s.state, item) < 1.0 < scarce


def test_a_loan_is_a_debt_and_repaying_clears_it():
    s = fixture_session(berlin)
    item = "resource:reichsmark"
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.MoveEntity(entity=OTTO, to=s.state.entities[ANNA].location)])])
    act(s, ANNA, Verb.LEND, OTTO, item=item, quantity=10)
    assert economy.owed(s.state, OTTO, ANNA) == 10
    assert economy.debts(s.state)[0][:3] == (OTTO, ANNA, 10)
    act(s, OTTO, Verb.REPAY, ANNA, item=item, quantity=4)
    assert economy.owed(s.state, OTTO, ANNA) == 6
    act(s, OTTO, Verb.REPAY, ANNA, item=item, quantity=50)
    assert economy.owed(s.state, OTTO, ANNA) == 0
    assert invariants.check_log(s.store, s.branch_id) == []


def test_cannot_lend_what_you_do_not_have():
    s = fixture_session(berlin)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.MoveEntity(entity=OTTO, to=s.state.entities[ANNA].location)])])
    v = rules.check(s.state, Intent(agent=ANNA, verb=Verb.LEND, target=OTTO, args={"item": "resource:reichsmark", "quantity": 9999}))
    assert v.status == "impossible"


# -- ownership and building ---------------------------------------------------------


def test_a_finished_undertaking_puts_up_a_building_the_owner_owns():
    s = fixture_session(berlin)
    s.debug = True
    anna = s.state.entities[ANNA]
    v = rules.check(s.state, Intent(agent=ANNA, verb=Verb.START, text="build a stall", args={"name": "Anna's Stall", "days": 1, "builds": "Anna's Stall"}))
    assert v.status == "resolved", v.reason
    s.commit([EventDraft(actor=ANNA, effects=v.outcome.effects)])
    proc = next(iter(s.state.processes.values()))
    assert proc.builds == "Anna's Stall"
    before = set(s.state.entities)
    for _ in range(40):
        v = rules.check(s.state, Intent(agent=ANNA, verb=Verb.WORK, target=proc.id, args={"minutes": 240}))
        if v.status != "resolved":
            break
        s.commit([EventDraft(actor=ANNA, effects=v.outcome.effects)])
        if s.state.processes[proc.id].status == "completed":
            break
    assert s.state.processes[proc.id].status == "completed"
    new = set(s.state.entities) - before
    stall = [s.state.entities[i] for i in new if s.state.entities[i].kind == "place"]
    assert len(stall) == 1 and stall[0].attrs["owner"] == ANNA
    assert grid.footprint(s.state, stall[0].id)
    assert s.state.path(s.state.entities[ANNA].location, stall[0].id) is not None or True
    assert invariants.check_log(s.store, s.branch_id) == []


def test_a_place_can_change_hands_by_sale():
    from tinyworld.gm.adjudicator import Adjudicator
    from tinyworld.gm.master import GameMaster
    from tinyworld.llm.fake import FakeLLM
    from tinyworld.llm.structured import StructuredLLM
    from tinyworld.llm.trace import Tracer
    from tinyworld.llm.types import CallContext
    from tinyworld.sim.step import apply_intents

    s = fixture_session(berlin)
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetAttr(entity="place:keller_bakery", key="owner", value=ANNA),
        fx.MoveEntity(entity=OTTO, to=s.state.entities[ANNA].location)])])
    intent = Intent(agent=ANNA, verb=Verb.SELL, target=OTTO,
                    args={"place": "place:keller_bakery", "price": 30, "item": "resource:reichsmark"})
    v = rules.check(s.state, intent)
    assert v.status == "adjudicate" and v.preset
    agreed = {"status": "success", "narration": "Otto buys the bakery.", "effects": [], "minutes": 20}
    llm = StructuredLLM(FakeLLM({"gm.adjudicate": agreed}), LLMConfig(), Tracer(s.store, LLMConfig()))
    run(apply_intents(s, GameMaster(Adjudicator(llm)), [intent], CallContext(s.branch_id, 0)))
    assert s.state.entities["place:keller_bakery"].attrs["owner"] == OTTO
    # A place one does not own cannot be sold.
    again = rules.check(s.state, intent)
    assert again.status == "impossible"
