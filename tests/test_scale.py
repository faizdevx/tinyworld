import asyncio
from datetime import datetime, timedelta

import pytest

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.state import Entity, Fact, Process, ProcessRequirements
from tinyworld.fixtures import toy
from tinyworld.god.channel import GodChannel
from tinyworld.god.parser import GodCommand
from tinyworld.llm import ledger
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig, Price
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.sim import tiers as tiering
from tinyworld.sim.budget import Budget
from tinyworld.sim.chronicler import Chronicle, ChronicleEvent, validate
from tinyworld.sim.loop import Simulation
from tinyworld.sim.scheduler import StepPolicy
from tinyworld.sim.tiers import TierPolicy
from tinyworld.sim.timeskip import DAY, TimeSkip, label, plan

YEAR = 365 * DAY


def run(coroutine):
    return asyncio.run(coroutine)


def priced_config(per_call=0.01):
    """Every model costs the same flat amount per million tokens, for easy sums."""
    config = LLMConfig()
    for model in list(config.prices):
        config.prices[model] = Price(1.0, 1.0, 0.0, 0.0)
    return config


def llm_for(session, fake, config=None):
    config = config or LLMConfig()
    return StructuredLLM(fake, config, Tracer(session.store, config))


def offline(session, seed="s", config=None, **options):
    fake = offline_llm(lambda: session.state, seed=seed)
    return Simulation(session, llm_for(session, fake, config), **options), fake


def system(session, *effects):
    session.commit([EventDraft(actor="system", effects=list(effects), visibility="god_only")])


def acting(fake):
    return [c for c in fake.calls if c.role.startswith("agent.act")]


# -- tiers -------------------------------------------------------------------


def test_tier1_agents_act_on_the_cheap_role_every_few_ticks():
    session = toy.build_toy()
    system(session, fx.SetAttr(entity=toy.LENA, key="tier", value=1))
    sim, fake = offline(session, tiers=TierPolicy(tier1_every=4, idle_events=10_000, promote_involved=False))
    run(sim.run(12))

    by_agent = {}
    for call in acting(fake):
        by_agent.setdefault(call.context.agent, set()).add(call.role)
    assert by_agent[toy.ANNA] == {"agent.act"} and by_agent[toy.LENA] == {"agent.act.tier1"}
    lena_turns = {c.context.tick_seq for c in acting(fake) if c.context.agent == toy.LENA}
    anna_turns = {c.context.tick_seq for c in acting(fake) if c.context.agent == toy.ANNA}
    assert len(anna_turns) == 12 and len(lena_turns) == 3
    assert LLMConfig().route("agent.act.tier1").tier == "cheap"


def test_tier1_prompt_is_shorter():
    session = toy.build_toy()
    sim, _ = offline(session)
    assert (sim.agent_tier1.memories_k, sim.agent_tier1.new_limit) == (3, 5)
    assert sim.agent.memories_k > sim.agent_tier1.memories_k


def test_tier2_people_never_decide():
    session = toy.build_toy()
    system(session, fx.SetAttr(entity=toy.OTTO, key="tier", value=2))
    sim, fake = offline(session)
    run(sim.run(6))
    assert toy.OTTO not in {c.context.agent for c in acting(fake)}


def test_sustained_inactivity_demotes_and_involvement_promotes():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY))
    cry = {"verb": "speak", "say": {"text": "Fresh bread!", "channel": "audible"}}
    script = {
        toy.ANNA: [cry] * 6
        + [{"verb": "speak", "say": {"text": "Lena, wake up.", "to": [toy.LENA]}}],
    }
    position = {"n": 0}

    def act(request):
        if request.context.agent != toy.ANNA:
            return {"verb": "wait"}
        position["n"] += 1
        return script[toy.ANNA][min(position["n"] - 1, 6)]

    fake = FakeLLM(
        {
            "agent.act": act,
            "memory.importance": lambda r: {"scores": [2] * r.user.count(". ")},
            "agent.reflect": {"insights": [], "beliefs": []},
        }
    )
    sim = Simulation(session, llm_for(session, fake), tiers=TierPolicy(idle_events=4))
    results = run(sim.run(8))

    demotions = [e for r in results for e in r.events if "Demoted" in e.narration]
    assert demotions and demotions[0].actor == "system"
    assert tiering.tier_of(session.state.entities[toy.OTTO]) == 1
    # Anna spoke to Lena after Lena had gone quiet: Lena is pulled back in.
    assert any(toy.LENA in r.promoted for r in results)
    assert tiering.tier_of(session.state.entities[toy.LENA]) == 0


def test_persona_less_person_drawn_into_events_gets_a_persona():
    session = toy.build_toy()
    system(
        session,
        fx.CreateEntity(
            entity=Entity(id="person:hans", kind="person", name="Hans", location=toy.BAKERY, attrs={"tier": 2, "age": 50})
        ),
    )
    speak = {"verb": "speak", "say": {"text": "Hans, a word.", "to": ["person:hans"]}}
    fake = offline_llm(lambda: session.state)
    fake.on("agent.act", lambda r: speak if r.context.agent == toy.ANNA else {"verb": "wait"})
    sim = Simulation(session, llm_for(session, fake))
    result = run(sim.tick())

    assert result.promoted == ["person:hans"]
    hans = session.state.entities["person:hans"]
    assert tiering.tier_of(hans) == 0 and persona_of(hans) is not None
    prompt = fake.calls_for("agent.persona")[0]
    assert "already exists in the world" in prompt.system and "Age now: 50" in prompt.user
    run(sim.tick())
    assert "person:hans" in {c.context.agent for c in acting(fake)}


def test_god_targeting_can_promote():
    session = toy.build_toy()
    system(session, fx.SetAttr(entity=toy.OTTO, key="tier", value=1))
    sim, _ = offline(session)
    assert run(sim.promote([toy.OTTO], reason="chosen by the god")) == [toy.OTTO]
    assert tiering.tier_of(session.state.entities[toy.OTTO]) == 0
    assert run(sim.promote([toy.OTTO, toy.BAKERY, "person:nobody"])) == []


def test_age_follows_the_calendar():
    person = Entity(id="person:x", kind="person", name="X", attrs={"birth_date": "1930-06-15", "age": 0})
    assert tiering.age_of(person, datetime(1943, 6, 14)) == 12
    assert tiering.age_of(person, datetime(1943, 6, 15)) == 13
    assert not tiering.old_enough(person, datetime(1943, 6, 15))
    assert tiering.old_enough(person, datetime(1944, 6, 15))
    assert tiering.old_enough(Entity(id="person:y", kind="person", name="Y"), datetime(1943, 1, 1))


def test_background_drift_moves_groups_and_sags_under_hardship():
    session = toy.build_toy()
    system(
        session,
        fx.CreateEntity(entity=Entity(id="faction:guild", kind="faction", name="Guild", attrs={"morale": 50, "influence": 50})),
        fx.AssertFact(fact=Fact(id="fact:famine", text="A famine has begun.")),
        fx.AssertFact(fact=Fact(id="fact:drought", text="Drought continues.")),
    )
    draft = tiering.background_drift(session.state, "seed", periods=10)
    session.commit([draft])
    guild = session.state.entities["faction:guild"]
    assert guild.attrs["morale"] < 50 and guild.attrs["influence"] <= 50
    assert tiering.background_drift(toy.build_toy().state, "seed") is None


def test_daily_upkeep_notes_the_public_mood():
    session = toy.build_toy()
    sim, fake = offline(session, step_minutes=480)
    run(sim.run(4))
    assert len(fake.calls_for("tier2.summary")) == 1
    assert session.state.facts["fact:public_mood"].text.startswith("Public mood: People are getting by")


# -- step policy -------------------------------------------------------------


def events_of(session, **draft):
    return session.commit([EventDraft(**draft)]).events


def test_step_shortens_for_talk_and_lengthens_for_quiet():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY))
    policy = StepPolicy(min_minutes=30, base_minutes=60, max_minutes=480)
    state = session.state

    talk = events_of(session, kind="utterance", actor=toy.ANNA, effects=[fx.Utter(speaker=toy.ANNA, text="Hello")])
    action = events_of(session, actor=toy.ANNA, effects=[fx.MoveEntity(entity=toy.ANNA, to=toy.SQUARE)])
    idle = events_of(session, actor=toy.ANNA, narration="Anna waits.")

    assert policy.activity(talk) == "talk" and policy.activity(action) == "action"
    assert policy.activity(idle) == "quiet" and policy.activity([]) == "quiet"
    assert policy.next_step(state, talk, 60) == 30
    assert policy.next_step(state, action, 30) == 60
    assert policy.next_step(state, idle, 60) == 120
    assert policy.next_step(state, idle, 480) == 480
    assert policy.next_step(state, action, 60, lengthen=True) == 120

    apart = toy.build_toy().state
    assert policy.next_step(apart, talk, 60) == 60  # nobody shares a room

    system(session, fx.AdvanceTime(minutes=16 * 60))
    assert session.state.sim_time.hour == 0
    assert policy.next_step(session.state, idle, 60) == 480


def test_loop_uses_the_policy_and_an_explicit_step_overrides_it():
    session = toy.build_toy()
    fake = FakeLLM({"agent.act": {"verb": "wait"}, "memory.importance": lambda r: {"scores": [1] * r.user.count(". ")}, "agent.reflect": {"insights": []}})
    sim = Simulation(session, llm_for(session, fake), policy=StepPolicy(base_minutes=60, max_minutes=240))
    steps = [run(sim.tick()).step_minutes for _ in range(4)]
    assert steps == [60, 120, 240, 240]
    assert run(sim.tick(step_minutes=15)).step_minutes == 15
    assert session.state.sim_time == toy.START + timedelta(minutes=60 + 120 + 240 + 240 + 15)


# -- budget ------------------------------------------------------------------


def spend(session, config, amount):
    """Record a call that costs exactly ``amount``."""
    from tinyworld.llm.types import CallContext, LLMRequest, LLMResult

    request = LLMRequest(role="agent.act", system="", user="", schema={}, context=CallContext(session.branch_id, session.state.seq, toy.ANNA))
    Tracer(session.store, config).record(
        request, config.route("agent.act"),
        LLMResult(text="{}", model=config.tiers["standard"], input_tokens=int(amount * 1_000_000)),
    )


def test_budget_levels_degrade_in_order():
    session = toy.build_toy()
    config = priced_config()
    budget = Budget(session.store, session.branch_id, run_cap=10.0, agent_cap=6.0)
    assert budget.level() == "ok" and budget.remaining() == 10.0
    spend(session, config, 7.0)
    assert budget.level() == "lengthen" and budget.agent_over_cap(toy.ANNA)
    spend(session, config, 1.5)
    assert budget.level() == "demote"
    spend(session, config, 1.5)
    assert budget.level() == "pause" and budget.remaining() == 0.0
    budget.raise_cap(5.0)
    assert budget.level() == "ok"
    assert Budget(session.store, session.branch_id).level() == "ok"


def test_paused_tick_makes_no_calls_and_changes_nothing():
    session = toy.build_toy()
    config = priced_config()
    sim, fake = offline(session, config=config, budget=Budget(session.store, session.branch_id, run_cap=1.0))
    spend(session, config, 1.0)
    head = session.state.seq
    results = run(sim.run(5))
    assert len(results) == 1 and results[0].paused
    assert fake.calls == [] and session.state.seq == head


def test_budget_is_never_exceeded_by_more_than_one_tick():
    session = toy.build_toy()
    config = priced_config()
    sim, _ = offline(session, config=config)
    costs = []
    for _ in range(3):
        before = ledger.total(session.store, session.branch_id).cost
        run(sim.tick())
        costs.append(ledger.total(session.store, session.branch_id).cost - before)
    largest = max(costs)
    assert largest > 0

    cap = ledger.total(session.store, session.branch_id).cost + largest * 6
    sim.budget = Budget(session.store, session.branch_id, run_cap=cap)
    results = run(sim.run(200))
    assert results[-1].paused and len(results) < 200
    assert cap <= ledger.total(session.store, session.branch_id).cost <= cap + largest * 1.5
    levels = [r.level for r in results]
    assert levels.index("lengthen") < levels.index("demote") < levels.index("pause")


def test_demote_level_runs_everyone_on_the_cheap_tier():
    session = toy.build_toy()
    config = priced_config()
    sim, fake = offline(session, config=config, budget=Budget(session.store, session.branch_id, run_cap=10.0))
    spend(session, config, 9.0)
    result = run(sim.tick())
    assert result.level == "demote"
    assert {c.role for c in acting(fake)} <= {"agent.act.tier1"}


def test_agent_over_its_own_cap_drops_to_the_cheap_tier():
    session = toy.build_toy()
    config = priced_config()
    sim, fake = offline(session, config=config, budget=Budget(session.store, session.branch_id, agent_cap=0.5), tiers=TierPolicy(tier1_every=1))
    spend(session, config, 0.6)
    run(sim.tick())
    roles = {c.context.agent: c.role for c in acting(fake)}
    assert roles[toy.ANNA] == "agent.act.tier1" and roles[toy.OTTO] == "agent.act"


# -- chronicle validation ----------------------------------------------------


def chronicle_event(**kwargs):
    return ChronicleEvent(**{"narration": "Something happened.", **kwargs})


def test_chronicle_events_by_or_on_the_dead_are_refused():
    session = toy.build_toy()
    system(session, fx.Kill(entity=toy.OTTO))
    state = session.state
    for bad, why in [
        (chronicle_event(participants=[toy.OTTO]), "dead and cannot take part"),
        (chronicle_event(effects=[fx.SetAttr(entity=toy.OTTO, key="occupation", value="king")]), "is dead"),
        (chronicle_event(effects=[fx.Utter(speaker=toy.OTTO, text="Boo")]), "cannot speak"),
        (chronicle_event(effects=[fx.Kill(entity=toy.OTTO)]), "already dead"),
        (chronicle_event(effects=[fx.TransferItem(item=toy.COIN, quantity=1, source=toy.ANNA, dest=toy.OTTO)]), "is dead"),
        (chronicle_event(participants=["person:nobody"]), "not a person"),
        (chronicle_event(location="place:atlantis"), "not a place"),
        (chronicle_event(effects=[fx.SetRule(key="x", value=1)]), "not available"),
        (chronicle_event(effects=[fx.AdvanceTime(minutes=5)]), "not available"),
        (chronicle_event(effects=[fx.SetAttr(entity=toy.ANNA, key="tier", value=2)]), "cannot be changed"),
    ]:
        after, reason = validate(state, bad)
        assert after is None and why in reason, (bad, reason)

    inheritance = chronicle_event(
        participants=[toy.ANNA],
        effects=[fx.TransferItem(item=toy.COIN, quantity=10, source=toy.OTTO, dest=toy.ANNA), fx.Kill(entity=toy.LENA)],
    )
    after, _ = validate(state, inheritance)
    assert after.entities[toy.ANNA].inventory[toy.COIN] == 22 and not after.entities[toy.LENA].alive
    assert state.entities[toy.LENA].alive


def institute(**requirements):
    return Process(
        id="process:institute", name="Founding a physics institute", owner=toy.OTTO,
        location=toy.TOWN_HALL, work_minutes=10_000,
        requirements=ProcessRequirements(**requirements),
        outcome=Fact(id="fact:institute", text="The town has a physics institute."),
    )


def test_undertakings_cannot_progress_without_what_they_need():
    session = toy.build_toy()
    system(session, fx.StartProcess(process=institute(items={toy.GRAIN: 5}, facts=["fact:charter"], participants=[toy.LENA])))
    advance = chronicle_event(effects=[fx.AdvanceProcess(process_id="process:institute", delta=0.5)])
    after, reason = validate(session.state, advance)
    assert after is None and "needs 5 grain, has 0" in reason and "requires: fact:charter" in reason

    system(
        session,
        fx.ChangeQuantity(holder=toy.TOWN_HALL, item=toy.GRAIN, delta=5),
        fx.AssertFact(fact=Fact(id="fact:charter", text="A charter was granted.")),
    )
    after, _ = validate(session.state, advance)
    assert after.processes["process:institute"].progress == 0.5

    early = chronicle_event(effects=[fx.EndProcess(process_id="process:institute", status="completed")])
    assert "only 0% done" in validate(session.state, early)[1]
    abandon = chronicle_event(effects=[fx.EndProcess(process_id="process:institute", status="abandoned")])
    assert validate(session.state, abandon)[0] is not None

    system(session, fx.Kill(entity=toy.LENA))
    assert "Lena Vogel is gone" in validate(session.state, advance)[1]


# -- time skip ---------------------------------------------------------------


def test_skip_plans_periods_by_length():
    assert plan(3 * DAY) == [DAY] * 3
    assert plan(60 * DAY) == [7 * DAY] * 8 + [4 * DAY]
    assert plan(2 * YEAR) == [30 * DAY] * 24 + [10 * DAY]
    assert plan(20 * YEAR) == [YEAR] * 20
    assert [label(m) for m in (DAY, 7 * DAY, 30 * DAY, YEAR, 3 * YEAR)] == ["1 day", "1 week", "1 month", "1 year", "3 years"]
    with pytest.raises(ValueError):
        plan(0)


def scripted_skip(session, chronicles):
    fake = offline_llm(lambda: session.state)
    fake.on("chronicler", chronicles)
    sim = Simulation(session, llm_for(session, fake))
    return TimeSkip(sim), sim, fake


def test_skip_commits_valid_events_and_drops_invalid_ones():
    session = toy.build_toy()
    chronicle = {
        "summary": "A hard month of short rations.",
        "events": [
            {"narration": "Otto Brandt died of a fever.", "participants": [toy.OTTO], "effects": [{"type": "Kill", "entity": toy.OTTO, "cause": "fever"}], "importance": 9},
            {"narration": "Otto Brandt gave a speech.", "participants": [toy.OTTO], "effects": [{"type": "Utter", "speaker": toy.OTTO, "text": "Citizens!"}]},
            {"narration": "Lena Vogel moved into town.", "participants": [toy.LENA], "location": toy.SQUARE, "effects": [{"type": "MoveEntity", "entity": toy.LENA, "to": toy.TAVERN}], "importance": 5},
            {"narration": "The laws of nature changed.", "effects": [{"type": "SetRule", "key": "gravity", "value": 0}]},
        ],
    }
    skipper, sim, fake = scripted_skip(session, chronicle)
    result = run(skipper.skip(DAY))

    assert result.complete and result.periods == 1
    assert session.state.sim_time == toy.START + timedelta(days=1)
    chronicled = [e for e in result.events if e.kind == "chronicle"]
    assert [e.narration for e in chronicled] == ["Otto Brandt died of a fever.", "Lena Vogel moved into town."]
    assert all(e.actor == "gm" and e.trace_id for e in chronicled)
    assert [narration for narration, _ in result.rejected] == ["Otto Brandt gave a speech.", "The laws of nature changed."]
    assert "dead and cannot take part" in result.rejected[0][1]
    assert not session.state.entities[toy.OTTO].alive and "gravity" not in session.state.rules

    lena = sim.memory.list(session.branch_id, toy.LENA, kinds=("summary",))[-1]
    assert "Over 1 day" in lena.text and "A hard month of short rations." in lena.text
    assert "For me: Lena Vogel moved into town." in lena.text and lena.importance == 0.5
    anna = sim.memory.list(session.branch_id, toy.ANNA, kinds=("summary",))[-1]
    assert "For me" not in anna.text and anna.importance == 0.3
    assert "Standing facts" in fake.calls_for("chronicler")[0].user
    assert session.store.state_at(session.branch_id, use_snapshots=False) == session.state


def test_skip_fires_scheduled_events_and_ages_people():
    session = toy.build_toy()
    channel = GodChannel(None)
    run(channel.apply(session, "t", [GodCommand(op="change_environment", description="A drought begins.", when="1943-06-01")]))
    run(channel.apply(session, "t", [GodCommand(op="spawn", kind="person", name="Eva Roth", location=toy.TAVERN, attrs={"age": 40})]))
    skipper, sim, _ = scripted_skip(session, {"summary": "Quiet.", "events": []})
    run(skipper.skip(2 * YEAR + 10 * DAY))
    assert session.state.fact_holds("fact:a_drought_begins")
    assert session.state.entities["person:eva_roth"].attrs["age"] == 42
    # People seeded with only an age are given a birth date and age too.
    assert session.state.entities[toy.ANNA].attrs["birth_date"] == "1909-03-14"
    assert session.state.entities[toy.ANNA].attrs["age"] == 36
    assert session.state.sim_time == toy.START + timedelta(days=740)


def test_skip_stops_when_the_budget_runs_out():
    session = toy.build_toy()
    config = priced_config()
    fake = offline_llm(lambda: session.state)
    sim = Simulation(session, llm_for(session, fake, config))
    result = run(TimeSkip(sim).skip(3 * YEAR + 1))
    per_period = ledger.total(session.store, session.branch_id).cost / result.periods

    second = toy.build_toy()
    fake = offline_llm(lambda: second.state)
    budget = Budget(second.store, second.branch_id, run_cap=per_period * 5)
    sim = Simulation(second, llm_for(second, fake, config), budget=budget)
    stopped = run(TimeSkip(sim).skip(20 * YEAR))
    assert stopped.stopped == "budget" and not stopped.complete
    assert 4 <= stopped.periods <= 7
    assert budget.spent() <= budget.run_cap + per_period * 1.5
    assert second.state.sim_time == toy.START + timedelta(days=365 * stopped.periods)


def test_twenty_year_skip_fits_the_budget_and_never_breaks_an_invariant():
    session = toy.build_toy()
    config = priced_config()
    run(GodChannel(None).apply(session, "t", [GodCommand(op="start_process", name="Build a dam", target=toy.OTTO, location=toy.SQUARE)]))
    fake = offline_llm(lambda: session.state, seed="long")
    budget = Budget(session.store, session.branch_id, run_cap=0.5)
    sim = Simulation(session, llm_for(session, fake, config), budget=budget)
    result = run(TimeSkip(sim).skip(20 * YEAR))

    assert result.complete and result.periods == 20 and result.stopped is None
    assert budget.spent() < budget.run_cap
    assert session.state.sim_time == toy.START + timedelta(days=365 * 20)
    assert session.state.processes["process:build_a_dam"].status == "completed"
    assert session.state.entities[toy.ANNA].attrs["age"] == 53
    chronicled = [e for e in result.events if e.kind == "chronicle"]
    assert len(chronicled) >= 5 and result.rejected == []

    # Replaying the stored log from nothing reproduces the state: every
    # committed event was applicable in the order it was committed.
    assert session.store.state_at(session.branch_id, use_snapshots=False) == session.state
    dead = set()
    for event in session.store.events(session.branch_id):
        assert event.actor not in dead
        dead |= {e.entity for e in event.effects if isinstance(e, fx.Kill)}


# -- exit: promotion after a skip matches the chronicle ----------------------

CHILD = {
    "age": 0,
    "persona": {
        "summary": "A newborn with a rare gift for numbers.",
        "aptitudes": {"physics": 10, "mathematics": 10},
        "knowledge": {"knows": [], "does_not_know": ["everything; a newborn"]},
    },
    "explanation": "A new person, not the historical one.",
}

GROWN = {
    "age": 20,
    "occupation": "physics student",
    "persona": {
        "summary": "A brilliant, restless student who taught himself from library books.",
        "traits": ["brilliant", "restless"],
        "goals": ["study in Berlin", "understand the atom"],
        "fears": ["being conscripted"],
        "aptitudes": {"physics": 3},
        "knowledge": {"knows": ["school physics", "the town"], "does_not_know": ["anything outside his reading"]},
    },
    "explanation": "",
}


def test_child_promoted_after_a_skip_has_the_history_the_chronicle_gave_him():
    session = toy.build_toy()
    fake = offline_llm(lambda: session.state)
    fake.on("agent.persona", [CHILD, GROWN])
    llm = llm_for(session, fake)
    channel = GodChannel(llm)
    born = run(channel.apply(session, "t", [GodCommand(op="spawn", kind="person", name="Albert Einstein", location="a house", description="a newborn")]))
    assert born.applied
    child_id = "person:albert_einstein"

    years = iter(
        [
            {"summary": "A quiet year.", "events": []},
            {"summary": "School began.", "events": [
                {"narration": "Albert Einstein astonished the schoolmaster with his sums.", "participants": [child_id], "importance": 6},
            ]},
        ]
        + [{"summary": "Years passed.", "events": []}] * 10
        + [{"summary": "A discovery.", "events": [
            {"narration": "Albert Einstein built a wireless set from scrap.", "participants": [child_id],
             "effects": [{"type": "SetAttr", "entity": child_id, "key": "occupation", "value": "apprentice"}], "importance": 7},
        ]}]
        + [{"summary": "Years passed.", "events": []}] * 20
    )
    fake.on("chronicler", lambda request: next(years))
    sim = Simulation(session, llm)
    result = run(TimeSkip(sim).skip(20 * YEAR))
    assert result.complete

    albert = session.state.entities[child_id]
    assert albert.attrs["age"] == 19 and tiering.tier_of(albert) == 0
    persona = persona_of(albert)
    assert persona.summary.startswith("A brilliant, restless student")
    assert persona.goals == ["study in Berlin", "understand the atom"]
    # The inborn gift survives the rewrite.
    assert persona.aptitudes == {"physics": 10, "mathematics": 10}
    assert albert.attrs["occupation"] == "physics student"

    promotion = [c for c in fake.calls_for("agent.persona") if "already exists" in c.system][0]
    assert "astonished the schoolmaster" in promotion.user
    assert "built a wireless set from scrap" in promotion.user
    assert "Age now: 14" in promotion.user
    promoted_at = [e for e in session.store.events(session.branch_id) if "come of age" in e.narration]
    assert len(promoted_at) == 1 and promoted_at[0].sim_time.year == 1958

    memories = sim.memory.list(session.branch_id, child_id)
    life = [m for m in memories if m.text.startswith("My life so far")]
    assert len(life) == 1
    assert "A child, Albert Einstein, is born." in life[0].text
    assert "astonished the schoolmaster" in life[0].text
    assert "built a wireless set from scrap" in life[0].text
    # He remembers nothing from before he had a mind of his own, except as that story.
    assert memories[0].id == life[0].id

    # He now decides for himself, and his prompt carries that past.
    fake.on("agent.act", {"verb": "wait"})
    run(sim.tick())
    prompt = [c for c in fake.calls_for("agent.act") if c.context.agent == child_id][-1].user
    assert "You are Albert Einstein" in prompt and "understand the atom" in prompt


# -- replay with cost-driven decisions ---------------------------------------


def test_replay_reproduces_budget_driven_behaviour():
    session = toy.build_toy()
    config = priced_config()
    start = session.state.seq
    sim, _ = offline(session, config=config, policy=StepPolicy(), tiers=TierPolicy(tier1_every=2))
    run(sim.run(3))
    cap = ledger.total(session.store, session.branch_id).cost * 2.2
    sim.budget = Budget(session.store, session.branch_id, run_cap=cap)
    run(sim.run(40))
    recorded = session.store.events(session.branch_id, after=start)

    replay = session.fork(start, "replay")
    replay_llm = StructuredLLM(ReplayLLM(session.store, session.branch_id), config, Tracer(session.store, config))
    again = Simulation(replay, replay_llm, policy=StepPolicy(), tiers=TierPolicy(tier1_every=2))
    run(again.run(3))
    again.budget = Budget(session.store, replay.branch_id, run_cap=cap)
    run(again.run(40))
    replayed = session.store.events(replay.branch_id, after=start)

    strip = lambda events: [e.model_dump(exclude={"branch_id", "trace_id"}) for e in events]
    assert strip(replayed) == strip(recorded)
    assert ledger.total(session.store, replay.branch_id).cost == pytest.approx(
        ledger.total(session.store, session.branch_id).cost
    )
