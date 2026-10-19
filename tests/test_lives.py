import asyncio
import random

from tinyworld.core import effects as fx
from tinyworld.core.entropy import Entropy, Fixed
from tinyworld.core.events import EventDraft
from tinyworld.core.state import Entity
from tinyworld.eval import invariants
from tinyworld.eval.v7_experiments import fixture_session, town_for
from tinyworld.fixtures import berlin
from tinyworld.llm.router import LLMConfig
from tinyworld.sim import years
from tinyworld.sim.replay import replay
from tinyworld.sim.tiers import birth_date_for
from tinyworld.sim.town import Town
from tinyworld.sim.watch import why
from tinyworld.world import lives
from tinyworld.world.cast import CastLibrary

ANNA, OTTO, LENA, FRIEDRICH = "person:anna_keller", "person:otto_brandt", "person:lena_vogel", "person:friedrich_brandt"


class Seeded(Entropy):
    """Entropy from a fixed seed, so a long run in a test is the same every time."""

    def __init__(self, seed, store=None, branch=None, seq=lambda: 0):
        super().__init__(store, branch, seq=seq)
        self._os = random.Random(seed)


def run(c):
    return asyncio.run(c)


def town(**kw):
    s = fixture_session(berlin, laid_out=False)
    base = town_for(s, chaos=0.0, petitioning=False, paper=False)
    return Town(base.sim, base.entropy, paper=False, petitioning=False, chaos=0.0, **kw), s


def warm(s, a, b, value=70):
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetRelation(source=a, dest=b, kind="love", value=value), fx.SetRelation(source=b, dest=a, kind="love", value=value)])])


def add_person(s, name, age, t=None):
    pid = "person:" + name.lower().replace(" ", "_")
    (t.commit if t is not None else s.commit)([EventDraft(actor="system", visibility="god_only", effects=[fx.CreateEntity(entity=Entity(
        id=pid, kind="person", name=name, location="place:market_square",
        attrs={"age": age, "tier": 0, "birth_date": birth_date_for(s.state.sim_time, age),
               "persona": {"summary": name, "aptitudes": {"craft": 6}, "traits": ["steady"]}}))])])
    return pid


def test_two_close_adults_can_marry_and_kin_cannot():
    t, s = town()
    warm(s, ANNA, FRIEDRICH)
    a, f = s.state.entities[ANNA], s.state.entities[FRIEDRICH]
    assert lives.eligible(s.state, a, f)
    drafts = lives.marriages(s.state, 365 * 1440 * 3, Fixed([0.0]))
    assert drafts and "marry" in drafts[0].narration
    s.commit(drafts)
    assert lives.spouse_of(s.state, ANNA) == FRIEDRICH
    assert not lives.eligible(s.state, a, s.state.entities[OTTO])


def test_a_child_has_two_parents_inherits_and_waits_to_grow_up():
    t, s = town()
    warm(s, ANNA, FRIEDRICH)
    s.commit(lives.marriages(s.state, 365 * 1440 * 3, Fixed([0.0])))
    draft = lives.birth_draft(s.state, s.state.entities[ANNA], s.state.entities[FRIEDRICH], Fixed([0.0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5]))
    s.commit([draft])
    child = [p for p in s.state.people() if p.attrs.get("status") == "child"][0]
    assert set(lives.parents_of(child)) == {ANNA, FRIEDRICH}
    assert child.attrs["tier"] == 2 and child.attrs["age"] == 0
    parent_apt = s.state.entities[ANNA].attrs["persona"]["aptitudes"]
    assert set(child.attrs["persona"]["aptitudes"]) >= set(parent_apt)
    assert lives.children_of(s.state, ANNA)[0].id == child.id


def test_the_dead_leave_goods_property_and_debts_to_an_heir():
    t, s = town()
    warm(s, ANNA, FRIEDRICH)
    s.commit(lives.marriages(s.state, 365 * 1440 * 3, Fixed([0.0])))
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[
        fx.SetAttr(entity="place:keller_bakery", key="owner", value=ANNA),
        fx.SetRelation(source=ANNA, dest=OTTO, kind="owes", value=7, note="resource:reichsmark")])])
    anna = s.state.entities[ANNA]
    coin = anna.inventory["resource:reichsmark"]
    s.commit([lives.death_draft(s.state, anna, "illness")])
    s.commit([lives.inheritance_draft(s.state, s.state.entities[ANNA], s.state.seq)])
    f = s.state.entities[FRIEDRICH]
    assert s.state.entities["place:keller_bakery"].attrs["owner"] == FRIEDRICH
    assert f.inventory["resource:reichsmark"] >= coin
    rel = s.state.relation(FRIEDRICH, OTTO)
    assert rel.kind == "owes" and rel.value == 7


def test_old_age_is_deadlier_than_youth_and_sickness_than_health():
    assert lives.yearly_hazard(80) > lives.yearly_hazard(30) * 10
    assert lives.yearly_hazard(40, 20) > lives.yearly_hazard(40, 100) * 3


def test_a_thirty_year_skip_produces_a_family_with_three_generations():
    t, s = town()
    s.debug = True
    people = [add_person(s, n, a) for n, a in (("Ada Weiss", 22), ("Bruno Weiss", 24), ("Carla Stein", 21), ("Dario Stein", 23))]
    warm(s, people[0], people[1], 80)
    warm(s, people[2], people[3], 80)
    counts = run(years.skip(t, 30, Seeded(7, s.store, s.branch_id, lambda: s.state.seq)))
    assert counts["marriages"] >= 1 and counts["births"] >= 2 and counts["choices"] > 20
    best = max(lives.generations(s.state, p) for p in people)
    assert best >= 3, counts
    assert invariants.check_log(s.store, s.branch_id) == []


def test_a_grandchilds_choice_traces_back_to_a_grandparent():
    t, s = town()
    a, b = add_person(s, "Ada Weiss", 22), add_person(s, "Bruno Weiss", 24)
    warm(s, a, b, 90)
    run(years.skip(t, 62, Seeded(7, s.store, s.branch_id, lambda: s.state.seq)))
    state = s.state
    grand = []
    for p in state.people(alive=False):
        for q in lives.parents_of(p):
            if q in state.entities and lives.parents_of(state.entities[q]):
                grand.append(p)
                break
    assert grand, "no grandchild in 62 years"
    traced = False
    for kid in grand:
        acts = [e for e in s.store.events(s.branch_id, actor=kid.id) if e.kind == "action"]
        if not acts:
            continue
        graph = why(s.store, s.branch_id, acts[0].seq, depth=14)
        text = " ".join(n["narration"] for n in graph["nodes"])
        if "marry" in text and "is born" in text:
            traced = True
            break
    assert traced, "no grandchild who chose anything, with a line back through a marriage"


def test_a_skip_replays_exactly():
    t, s = town()
    add_person(s, "Ada Weiss", 22, t)
    run(years.skip(t, 6, Seeded(7, s.store, s.branch_id, lambda: s.state.seq)))
    report = run(replay(s.store, s.branch_id, LLMConfig()))
    assert report.identical, report.first_difference


def test_people_saved_to_the_cast_library_reappear_with_their_history():
    t, s = town()
    lib = CastLibrary(s.store)
    cid = lib.save(t.sim, ANNA, note="She ran the bakery through the war.")
    state = s.state.model_copy(deep=True)
    state.entities.pop(ANNA)
    draft, notes = lib.appear(state, cid, "place:market_square")
    assert "arrives" in draft.narration
    assert notes and notes[0][1].startswith("My life so far") and "bakery" in notes[0][1]
    assert lib.all()[0]["name"] == "Anna Keller"
