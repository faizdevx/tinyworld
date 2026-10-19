import asyncio

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.eval import invariants
from tinyworld.eval.v7_experiments import fixture_session, town_for
from tinyworld.fixtures import berlin
from tinyworld.god.parser import GodCommand
from tinyworld.llm.router import LLMConfig
from tinyworld.sim.replay import replay
from tinyworld.sim.town import Town
from tinyworld.world import gods, petitions

ANNA, OTTO = "person:anna_keller", "person:otto_brandt"


def run(c):
    return asyncio.run(c)


def setup():
    s = fixture_session(berlin, laid_out=False)
    base = town_for(s, chaos=0.0, petitioning=False, paper=False)
    town = Town(base.sim, base.entropy, paper=False, petitioning=False, chaos=0.0, god=None)
    p = gods.Pantheon(s.store, s.world_id)
    p.add("ann", "Ann", "god")
    p.add("dem", "Demi", "demigod", points=7)
    p.add("obs", "Ola", "observer")
    p.add("ai", "The Rival", "god", ai=True, goal="make the Keller bakery fail")
    return town, s, p


def take_bread(god, qty, holder="place:keller_bakery"):
    c = GodCommand(op="modify", target=holder, item="resource:bread", quantity=qty)
    return gods.Act(god, "command", f"{qty:+d} bread", [c], targets={holder})


def test_an_observer_cannot_act_and_a_demigod_pays_and_is_limited():
    town, s, p = setup()
    acts = run(gods.run_window(town, p, [take_bread("obs", 1), take_bread("dem", 1)]))
    assert acts[0].result.startswith("refused") and "watching" in acts[0].result
    assert acts[1].done and p.members["dem"].points == 4
    spawn = gods.Act("dem", "command", "a stranger", [GodCommand(op="spawn", kind="person", name="Stranger", location="place:market_square")])
    run(gods.run_window(town, p, [spawn]))
    assert "not theirs" in spawn.result
    for _ in range(2):
        run(gods.run_window(town, p, [take_bread("dem", 1)]))
    broke = gods.Act("dem", "command", "more", [GodCommand(op="modify", target="place:keller_bakery", item="resource:bread", quantity=1)])
    run(gods.run_window(town, p, [broke]))
    assert "points" in broke.result


def test_a_demigods_points_come_back_each_day():
    town, s, p = setup()
    p.members["dem"].points = 0
    p.refill(s.state)
    first = p.members["dem"].points
    s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=1440)])])
    p.refill(s.state)
    assert p.members["dem"].points == min(p.members["dem"].cap, first + gods.DAILY_REFILL)


def test_two_gods_at_odds_over_one_thing_cannot_both_have_it_and_the_world_hears():
    town, s, p = setup()
    before = s.state.entities["place:keller_bakery"].inventory["resource:bread"]
    mine = take_bread("ann", 5)
    theirs = take_bread("ai", -5)
    acts = run(gods.run_window(town, p, [theirs, mine]))
    done = [a for a in acts if a.done]
    assert len(done) == 1
    assert s.state.entities["place:keller_bakery"].inventory["resource:bread"] in (before + 5, before - 5)
    assert any(f.startswith("fact:gods_disagree_") for f in s.state.facts)
    heard = [m for who in (ANNA, OTTO) for m in town.sim.memory.list(s.branch_id, who) if "gods disagree" in m.text]
    assert heard, "no resident noticed"


def test_a_god_outranks_a_demigod_and_equals_are_settled_by_a_recorded_draw():
    town, s, p = setup()
    acts = run(gods.run_window(town, p, [take_bread("dem", 1), take_bread("ann", -1)]))
    assert [a.god for a in acts if a.done] == ["ann"]
    a, b = take_bread("ann", 1), take_bread("ai", -1)
    draws = []
    for seed in (0.1, 0.9):
        from tinyworld.core.entropy import Fixed

        town.entropy = Fixed([seed, 1 - seed] * 3)
        out, clashes = p.resolve([take_bread("ann", 1), take_bread("ai", -1)], town.entropy)
        draws.append(out[0].god)
    assert set(draws) == {"ann", "ai"}


def test_the_ai_god_acts_on_its_goal_with_the_same_powers():
    town, s, p = setup()
    before = s.state.entities["place:keller_bakery"].inventory.get("resource:bread", 0)
    ai = gods.AIGod("ai", "make the Keller bakery fail")
    acts = run(ai.decide(town, town.entropy))
    assert acts and acts[0].kind == "command"
    run(gods.run_window(town, p, acts))
    assert s.state.entities["place:keller_bakery"].inventory.get("resource:bread", 0) < before


def test_two_people_and_an_ai_god_share_a_world_without_breaking_an_invariant():
    town, s, p = setup()
    s.debug = True
    ai = gods.AIGod("ai", "make the Keller bakery fail")
    for round_ in range(4):
        acts = [take_bread("ann", 2), take_bread("dem", -1, "place:town_hall")] if round_ % 2 == 0 else [take_bread("ann", -2)]
        acts += run(ai.decide(town, town.entropy))
        run(gods.run_window(town, p, acts))
        s.commit([EventDraft(actor="system", visibility="god_only", effects=[fx.AdvanceTime(minutes=1440)])])
    assert invariants.check_log(s.store, s.branch_id) == []
    assert any(f.startswith("fact:gods_disagree_") for f in s.state.facts)


def test_divine_acts_replay_exactly():
    town, s, p = setup()
    run(gods.run_window(town, p, [take_bread("ann", 3), take_bread("ai", -3)]))
    report = run(replay(s.store, s.branch_id, LLMConfig()))
    assert report.identical, report.first_difference


def test_roles_persist_with_the_world():
    town, s, p = setup()
    again = gods.Pantheon(s.store, s.world_id)
    assert again.members["dem"].points == 7 and again.members["ai"].ai
