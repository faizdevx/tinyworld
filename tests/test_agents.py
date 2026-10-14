import asyncio
import re
from datetime import datetime, timedelta

import pytest

from tinyworld.agents import retrieval
from tinyworld.agents.agent import Agent
from tinyworld.agents.beliefs import Belief, BeliefStore, compare_beliefs, trust, truth
from tinyworld.agents.memory import Compactor, ImportanceScorer, MemoryStore, NewMemory
from tinyworld.agents.persona import persona_of, render
from tinyworld.agents.planner import Planner
from tinyworld.agents.reflection import Reflector
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft, Verb
from tinyworld.fixtures import toy
from tinyworld.gm.perception import perceive
from tinyworld.llm.embed import HashEmbedder
from tinyworld.llm.fake import FakeLLM
from tinyworld.llm.offline import offline_llm
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.llm.types import CallContext
from tinyworld.sim.loop import Simulation


def run(coroutine):
    return asyncio.run(coroutine)


def llm_for(session, fake):
    return StructuredLLM(fake, LLMConfig(), Tracer(session.store, LLMConfig()))


def system(session, *effects):
    session.commit([EventDraft(actor="system", effects=list(effects), visibility="god_only")])


def memory_item(text, seq, when, **kwargs):
    return NewMemory(kind="observation", text=text, created_seq=seq, sim_time=when, **kwargs)


WAIT = {"verb": "wait", "text": "wait"}


def scripted(by_agent, **extra):
    """A FakeLLM whose agents follow per-agent scripts; everyone else waits."""
    positions: dict[str, int] = {}

    def act(request):
        agent = request.context.agent
        script = by_agent.get(agent, [WAIT])
        index = positions.get(agent, 0)
        positions[agent] = index + 1
        return script[min(index, len(script) - 1)]

    handlers = {
        "agent.act": act,
        "memory.importance": lambda r: {
            "scores": [3] * len(re.findall(r"^\d+\. ", r.user, re.MULTILINE))
        },
        "agent.reflect": {"insights": [], "beliefs": []},
        "memory.summarize": {"text": "Earlier days.", "importance": 2},
    }
    handlers.update(extra)
    return FakeLLM(handlers)


# -- persona -----------------------------------------------------------------


def test_persona_renders_identity_and_knowledge_boundary():
    anna = toy.build_toy().state.entities[toy.ANNA]
    text = render(anna, persona_of(anna))
    assert "You are Anna Keller [person:anna_keller]" in text
    assert "You fear: requisition of her flour" in text
    assert "You know nothing of: anything after March 1943" in text
    assert "Never draw on knowledge from outside" in text


def test_entities_without_a_valid_persona_have_none():
    state = toy.build_toy().state
    assert persona_of(state.entities[toy.BAKERY]) is None


# -- memory and retrieval ----------------------------------------------------


def test_memory_ids_are_deterministic_and_branch_aware():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    now = session.state.sim_time
    first = memory.write(
        session.branch_id, toy.ANNA,
        [memory_item("Saw Otto at the square.", 8, now), memory_item("Bread sold out.", 8, now)],
    )
    assert [m.id.rsplit(":", 2)[1:] for m in first] == [["8", "0"], ["8", "1"]]
    system(session, fx.AdvanceTime(minutes=1))
    child = session.fork(session.state.seq, "child")
    memory.write(child.branch_id, toy.ANNA, [memory_item("Only in the fork.", 9, now)])
    memory.write(session.branch_id, toy.ANNA, [memory_item("Only on main.", 9, now)])

    assert [m.text for m in memory.list(child.branch_id, toy.ANNA)] == [
        "Saw Otto at the square.", "Bread sold out.", "Only in the fork.",
    ]
    assert "Only in the fork." not in [m.text for m in memory.list(session.branch_id, toy.ANNA)]
    assert memory.list(session.branch_id, toy.ANNA)[0].embedding is not None


def test_retrieval_weighs_relevance_importance_recency_and_people():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    now = datetime(1943, 3, 20, 12, 0)
    old = now - timedelta(days=30)
    written = memory.write(
        session.branch_id, toy.ANNA,
        [
            memory_item("The mayor took grain from the bakery store.", 1, old, importance=0.9),
            memory_item("Rain fell on the square all morning.", 2, now, importance=0.1),
            memory_item("Lena laughed at a joke.", 3, old, importance=0.1, participants=[toy.LENA]),
            memory_item("The mayor counted grain sacks.", 4, old, importance=0.1, confidence=0.3),
        ],
    )
    query = memory.embedder.embed(["what did the mayor do with the grain"])[0]

    ranked = retrieval.retrieve(written, query=query, now=now, k=4)
    assert ranked[0].memory.text.startswith("The mayor took grain")
    assert ranked[0].parts["relevance"] > ranked[-1].parts["relevance"]

    by_text = {s.memory.text: s for s in ranked}
    assert by_text["Rain fell on the square all morning."].parts["recency"] == pytest.approx(1.0)
    assert by_text["Lena laughed at a joke."].parts["recency"] < 0.01

    with_lena = retrieval.retrieve(
        written, query=None, now=now, k=4, related=frozenset({toy.LENA})
    )
    scores = {s.memory.text: s.score for s in with_lena}
    assert scores["Lena laughed at a joke."] > scores["The mayor counted grain sacks."]
    assert retrieval.retrieve(written, query=query, now=now, k=1)[0].memory.importance == 0.9


def test_importance_scorer_uses_the_model_and_falls_back_to_a_heuristic():
    session = toy.build_toy()
    ctx = CallContext(session.branch_id, 1, toy.ANNA)
    texts = ["Otto walked past.", "Lena was arrested."]

    scored = run(ImportanceScorer(llm_for(session, FakeLLM({"memory.importance": {"scores": [2, 9]}}))).score("Anna", texts, ctx))
    assert scored == [0.2, 0.9]

    wrong_count = FakeLLM({"memory.importance": {"scores": [5]}})
    fallback = run(ImportanceScorer(llm_for(session, wrong_count)).score("Anna", texts, ctx, addressed=[True, False]))
    assert fallback == [0.5, 0.7]
    assert len(wrong_count.calls) == 3
    assert run(ImportanceScorer(None).score("Anna", texts, ctx)) == [0.3, 0.7]


def test_compaction_keeps_important_memories_retrievable():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    start = session.state.sim_time
    items = [
        memory_item(f"Routine day {i}: baked and sold bread.", i, start + timedelta(hours=i), importance=0.2)
        for i in range(70)
    ]
    items[5] = memory_item(
        "The mayor seized the grain store by decree.", 5, start + timedelta(hours=5), importance=0.9
    )
    memory.write(session.branch_id, toy.ANNA, items)

    fake = FakeLLM({"memory.summarize": {"text": "Weeks of routine baking.", "importance": 2}})
    compactor = Compactor(llm_for(session, fake), memory, max_active=60, batch=20)
    now = start + timedelta(hours=80)
    summary = run(compactor.compact(session.branch_id, toy.ANNA, "Anna", 71, now, CallContext(session.branch_id, 71, toy.ANNA)))

    active = memory.list(session.branch_id, toy.ANNA)
    assert summary.kind == "summary" and summary.text == "Weeks of routine baking."
    assert len(active) == 70 - 20 + 1
    assert len(memory.list(session.branch_id, toy.ANNA, include_superseded=True)) == 71
    assert "The mayor seized the grain store by decree." in [m.text for m in active]

    query = memory.embedder.embed(["mayor seized grain decree"])[0]
    best = retrieval.retrieve(active, query=query, now=now, k=3)
    assert best[0].memory.text == "The mayor seized the grain store by decree."

    again = run(compactor.compact(session.branch_id, toy.ANNA, "Anna", 72, now, CallContext(session.branch_id, 72, toy.ANNA)))
    assert again is None


def test_compaction_falls_back_to_plain_concatenation_without_a_model():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    now = session.state.sim_time
    memory.write(session.branch_id, toy.ANNA, [memory_item(f"Thing {i}.", i, now) for i in range(8)])
    summary = run(
        Compactor(None, memory, max_active=5, batch=4).compact(
            session.branch_id, toy.ANNA, "Anna", 9, now, CallContext(session.branch_id, 9)
        )
    )
    assert summary.text.startswith("Earlier: Thing 0. Thing 1.")


# -- beliefs -----------------------------------------------------------------


def test_trust_follows_the_relation():
    state = toy.build_toy().state
    assert trust(state, toy.LENA, toy.ANNA) == pytest.approx(0.85)
    assert trust(state, toy.ANNA, toy.OTTO) == pytest.approx(0.35)
    assert trust(state, toy.OTTO, toy.LENA) == pytest.approx(0.5)


def test_truth_reads_entities_and_facts():
    state = toy.build_toy().state
    assert truth(state, toy.ANNA, "location") == (True, toy.BAKERY)
    assert truth(state, toy.ANNA, "alive") == (True, True)
    assert truth(state, toy.OTTO, f"has:{toy.COIN}") == (True, 60)
    assert truth(state, toy.GRAIN, "rationed") == (True, True)
    assert truth(state, toy.OTTO, "hoards") == (False, None)


def _tell(session, speaker, listener, claim, location):
    result = session.commit(
        [
            EventDraft(
                kind="utterance", actor=speaker, location=location,
                effects=[fx.Utter(speaker=speaker, text="Listen.", addressees=[listener], claims=[claim])],
                narration=f"{speaker} tells {listener} something.",
            )
        ],
        observe=perceive,
    )
    return {o.observer: o for o in result.observed[0]}


def test_false_claim_from_a_trusted_source_becomes_a_wrong_belief():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY))
    beliefs = BeliefStore(session.store)
    lie = fx.Claim(subject=toy.GRAIN, predicate="rationed", value=False)

    seen = _tell(session, toy.ANNA, toy.LENA, lie, toy.BAKERY)
    adopted = beliefs.update_from_observation(session.branch_id, session.state, seen[toy.LENA], "m1")
    assert beliefs.update_from_observation(session.branch_id, session.state, seen[toy.ANNA]) == []

    belief = adopted[0]
    assert (belief.value, belief.source, belief.origin) == (False, toy.ANNA, "communication")
    assert belief.confidence == pytest.approx(0.85) and belief.evidence == ["m1"]

    report = compare_beliefs(session.state, beliefs.current(session.branch_id))
    assert len(report) == 1
    wrong = report[0]
    assert wrong.agent == toy.LENA and wrong.truth_known and wrong.correct is False
    assert (wrong.believed, wrong.actual) == (False, True)


def test_distrusted_speakers_are_believed_less_and_do_not_displace_a_firm_belief():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.OTTO, to=toy.BAKERY), fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY))
    beliefs = BeliefStore(session.store)
    branch = session.branch_id

    seen = _tell(session, toy.LENA, toy.ANNA, fx.Claim(subject=toy.OTTO, predicate="hoards", value="nothing"), toy.BAKERY)
    beliefs.update_from_observation(branch, session.state, seen[toy.ANNA])
    seen = _tell(session, toy.OTTO, toy.ANNA, fx.Claim(subject=toy.OTTO, predicate="hoards", value="grain"), toy.BAKERY)
    assert beliefs.update_from_observation(branch, session.state, seen[toy.ANNA]) == []
    held = beliefs.get(branch, toy.ANNA, toy.OTTO, "hoards")
    assert held.value == "nothing" and held.source == toy.LENA


def test_seeing_beats_hearing():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY), fx.MoveEntity(entity=toy.OTTO, to=toy.BAKERY))
    beliefs = BeliefStore(session.store)
    branch = session.branch_id

    result = session.commit(
        [EventDraft(actor=toy.OTTO, location=toy.BAKERY, effects=[fx.MoveEntity(entity=toy.OTTO, to=toy.SQUARE)], narration="Otto leaves for the square.")],
        observe=perceive,
    )
    watched = {o.observer: o for o in result.observed[0]}
    beliefs.update_from_observation(branch, session.state, watched[toy.LENA])
    assert beliefs.get(branch, toy.LENA, toy.OTTO, "location").origin == "observation"

    seen = _tell(session, toy.ANNA, toy.LENA, fx.Claim(subject=toy.OTTO, predicate="location", value=toy.TAVERN), toy.BAKERY)
    assert beliefs.update_from_observation(branch, session.state, seen[toy.LENA]) == []
    assert beliefs.get(branch, toy.LENA, toy.OTTO, "location").value == toy.SQUARE


def test_beliefs_follow_the_branch():
    session = toy.build_toy()
    beliefs = BeliefStore(session.store)
    now = session.state.sim_time

    def believe(branch, value, seq):
        beliefs.add(branch, Belief(agent=toy.ANNA, subject="x", predicate="p", value=value, confidence=0.5, origin="prior", as_of_seq=seq, as_of=now))

    believe(session.branch_id, "old", 3)
    system(session, fx.AdvanceTime(minutes=1))
    child = session.fork(session.state.seq, "child")
    believe(session.branch_id, "main-only", 9)
    believe(child.branch_id, "fork-only", 9)
    assert beliefs.get(session.branch_id, toy.ANNA, "x", "p").value == "main-only"
    assert beliefs.get(child.branch_id, toy.ANNA, "x", "p").value == "fork-only"


# -- reflection and planning -------------------------------------------------


def test_reflection_triggers_on_accumulated_importance_and_then_resets():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    beliefs = BeliefStore(session.store)
    fake = FakeLLM(
        {
            "agent.reflect": {
                "insights": [{"text": "Otto cannot be trusted with the grain.", "importance": 8}],
                "beliefs": [{"subject": toy.OTTO, "predicate": "trustworthy", "value": False, "confidence": 0.7}],
            }
        }
    )
    reflector = Reflector(llm_for(session, fake), memory, beliefs, threshold=1.0)
    branch, now = session.branch_id, session.state.sim_time

    memory.write(branch, toy.ANNA, [memory_item("Otto asked about flour.", 8, now, importance=0.4)])
    assert not reflector.due(branch, toy.ANNA)
    memory.write(branch, toy.ANNA, [memory_item("Otto took two sacks.", 9, now, importance=0.8)])
    assert reflector.due(branch, toy.ANNA)

    written = run(reflector.reflect(branch, toy.ANNA, "Anna", 10, now, CallContext(branch, 10, toy.ANNA)))
    assert [m.kind for m in written] == ["reflection"]
    assert written[0].importance == 0.8
    assert "Otto asked about flour." in fake.calls[0].user
    belief = beliefs.get(branch, toy.ANNA, toy.OTTO, "trustworthy")
    assert belief.origin == "inference" and belief.value is False
    assert not reflector.due(branch, toy.ANNA)


def test_failed_reflection_still_advances_the_marker():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    reflector = Reflector(llm_for(session, FakeLLM({"agent.reflect": "nonsense"})), memory, BeliefStore(session.store), threshold=0.5)
    branch, now = session.branch_id, session.state.sim_time
    memory.write(branch, toy.ANNA, [memory_item("Something big.", 8, now, importance=0.9)])
    run(reflector.reflect(branch, toy.ANNA, "Anna", 9, now, CallContext(branch, 9, toy.ANNA)))
    assert not reflector.due(branch, toy.ANNA)


def test_plan_is_stored_once_and_replaced_when_it_changes():
    session = toy.build_toy()
    memory = MemoryStore(session.store, HashEmbedder())
    planner = Planner(memory)
    branch, now = session.branch_id, session.state.sim_time
    assert planner.current(branch, toy.ANNA) == []
    planner.store(branch, toy.ANNA, ["open the shop", " ", "count the flour"], 8, now)
    planner.store(branch, toy.ANNA, ["open the shop", "count the flour"], 9, now)
    assert len(memory.list(branch, toy.ANNA, kinds=("plan",))) == 1
    planner.store(branch, toy.ANNA, ["hide the grain"], 10, now)
    assert planner.current(branch, toy.ANNA) == ["hide the grain"]
    assert Planner.should_reconsider([], []) and Planner.should_reconsider(["x"], [0.8])
    assert not Planner.should_reconsider(["x"], [0.3])


# -- agent -------------------------------------------------------------------


def build_agent(session, fake, digest="A small town under rationing."):
    memory = MemoryStore(session.store, HashEmbedder())
    return Agent(llm_for(session, fake), memory, BeliefStore(session.store), Planner(memory), world_digest=digest)


def act(session, agent, who=toy.ANNA, last_seen=-1):
    ctx = CallContext(session.branch_id, session.state.seq, who)
    return run(agent.act(session.state, session.state.entities[who], session.branch_id, ctx, last_seen))


def test_agent_prompt_carries_persona_surroundings_memories_and_plan():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY))
    fake = FakeLLM({"agent.act": {"thought": "Hm.", "verb": "move", "target": toy.SQUARE, "text": "look around", "plan": ["look around"]}})
    agent = build_agent(session, fake)
    now = session.state.sim_time
    agent.memory.write(session.branch_id, toy.ANNA, [memory_item("Otto demanded a list of grain stores.", 3, now, importance=0.8)])
    agent.memory.write(session.branch_id, toy.ANNA, [memory_item("Lena arrived at the bakery.", 9, now, importance=0.3)])
    agent.planner.store(session.branch_id, toy.ANNA, ["hide the flour"], 4, now)
    agent.beliefs.add(session.branch_id, Belief(agent=toy.ANNA, subject=toy.OTTO, predicate="hoards", value="grain", confidence=0.8, source=toy.LENA, origin="communication", as_of_seq=5, as_of=now))

    result = act(session, agent, last_seen=8)
    assert result.ok and result.intent.verb is Verb.MOVE and result.thought == "Hm."

    request = fake.calls[0]
    assert "playing one person" in request.system
    assert request.stable_context == "About this world:\nA small town under rationing."
    prompt = request.user
    assert "You are Anna Keller" in prompt and "You know nothing of" in prompt
    assert "Place: Keller Bakery" in prompt and "Lena Vogel [person:lena_vogel]" in prompt
    assert "Your view of Lena Vogel: employer (+60)" in prompt
    assert "person:otto_brandt hoards: grain (heard from Lena Vogel, sure)" in prompt
    since = prompt.split("Since you last decided:")[1]
    assert "Lena arrived at the bakery." in since.split("Your plan so far:")[0]
    remembered = prompt.split("Things you remember:")[1].split("Since you last decided:")[0]
    assert "Otto demanded a list of grain stores." in remembered
    assert "Lena arrived" not in remembered
    assert "1. hide the flour" in prompt
    assert agent.planner.current(session.branch_id, toy.ANNA) == ["look around"]


def test_agent_is_told_when_its_choice_is_impossible_and_tries_again():
    session = toy.build_toy()
    fake = FakeLLM(
        {
            "agent.act": [
                {"verb": "move", "target": "place:berlin", "text": "leave for the city"},
                {"verb": "speak", "say": {"text": "Otto!", "to": [toy.OTTO]}},
                {"verb": "move", "target": toy.SQUARE, "text": "go out"},
            ]
        }
    )
    result = act(session, build_agent(session, fake))
    assert result.ok and result.intent.target == toy.SQUARE
    assert "That cannot be done: that is not a place" in fake.calls[1].user
    assert "Otto Brandt is not here" in fake.calls[2].user


def test_agent_waits_when_the_model_is_unusable():
    session = toy.build_toy()
    result = act(session, build_agent(session, FakeLLM({"agent.act": {"verb": "fly"}})))
    assert not result.ok and result.intent.verb is Verb.WAIT


# -- the loop ----------------------------------------------------------------


def memories(sim, who):
    return sim.memory.list(sim.session.branch_id, who)


def test_memories_are_written_only_for_perceived_events():
    session = toy.build_toy()
    fake = scripted(
        {
            toy.ANNA: [{"verb": "speak", "text": "complain", "say": {"text": "The mayor is hoarding grain!", "channel": "audible"}}],
        }
    )
    sim = Simulation(session, llm_for(session, fake))
    result = run(sim.tick())

    spoken = [e for e in result.events if e.kind == "utterance"]
    assert len(spoken) == 1
    assert any("hoarding grain" in m.text for m in memories(sim, toy.ANNA))
    # Otto is in the town hall, Lena at the farm: neither is in earshot of the bakery.
    assert not any("hoarding" in m.text for m in memories(sim, toy.OTTO))
    assert not any("hoarding" in m.text for m in memories(sim, toy.LENA))
    assert all(m.source_events for m in memories(sim, toy.ANNA))
    assert session.state.sim_time == toy.START + timedelta(hours=1)


def test_a_lie_told_in_the_loop_becomes_the_listeners_false_belief():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY))
    fake = scripted(
        {
            toy.ANNA: [
                {
                    "verb": "speak",
                    "text": "mislead Lena",
                    "say": {
                        "text": "They lifted the grain ration yesterday.",
                        "to": [toy.LENA],
                        "message_type": "lie",
                        "claims": [{"subject": toy.GRAIN, "predicate": "rationed", "value": False}],
                    },
                }
            ]
        }
    )
    sim = Simulation(session, llm_for(session, fake))
    run(sim.tick())

    heard = [m for m in memories(sim, toy.LENA) if m.kind == "utterance_heard"]
    assert len(heard) == 1 and heard[0].participants == [toy.ANNA]
    report = compare_beliefs(session.state, sim.beliefs.current(session.branch_id, toy.LENA))
    wrong = [c for c in report if c.correct is False]
    assert len(wrong) == 1 and wrong[0].source == toy.ANNA
    assert sim.beliefs.current(session.branch_id, toy.ANNA) == []

    # Next tick the listener's prompt shows it as something she believes.
    run(sim.tick())
    lena_prompt = [c.user for c in fake.calls_for("agent.act") if c.context.agent == toy.LENA][-1]
    assert "resource:grain rationed: False (heard from Anna Keller, sure)" in lena_prompt
    assert "They lifted the grain ration yesterday." in lena_prompt


def test_impossible_choice_reaches_the_actor_as_private_feedback():
    session = toy.build_toy()
    system(session, fx.MoveEntity(entity=toy.LENA, to=toy.BAKERY), fx.ChangeQuantity(holder=toy.BAKERY, item=toy.BREAD, delta=-19))
    take = {"verb": "take", "target": toy.BAKERY, "args": {"item": toy.BREAD}, "text": "take the last loaf"}
    sim = Simulation(session, llm_for(session, scripted({toy.ANNA: [take], toy.LENA: [take]})))
    result = run(sim.tick())
    statuses = sorted(o.status for o in result.outcomes if o.intent.verb is Verb.TAKE)
    assert statuses == ["impossible", "success"]
    loser = next(o.intent.agent for o in result.outcomes if o.status == "impossible")
    assert any("could not do this" in m.text for m in memories(sim, loser))


def offline_sim(session, seed="s", **options):
    fake = offline_llm(lambda: session.state, seed=seed)
    return Simulation(session, llm_for(session, fake), **options), fake


def test_offline_world_runs_for_many_ticks():
    session = toy.build_toy()
    sim, fake = offline_sim(session, reflect_threshold=1.5)
    results = run(sim.run(30))

    assert session.state.sim_time == toy.START + timedelta(hours=30)
    actions = [e for r in results for e in r.events if e.actor.startswith("person:")]
    assert len(actions) > 40
    assert {e.kind for e in actions} >= {"action", "utterance"}
    assert sum(r.reflections for r in results) > 0
    assert sum(r.memories_written for r in results) > 40
    # Coins are neither created nor destroyed by anything agents can do.
    coins = sum(e.inventory.get(toy.COIN, 0) for e in session.state.entities.values())
    assert coins == 75
    assert session.store.state_at(session.branch_id, use_snapshots=False) == session.state


def comparable(events):
    return [e.model_dump(exclude={"branch_id", "trace_id"}) for e in events]


def test_full_loop_replays_offline_to_an_identical_event_log():
    session = toy.build_toy()
    start = session.state.seq
    sim, _ = offline_sim(session, reflect_threshold=1.5, max_active_memories=10)
    run(sim.run(12))

    replay = session.fork(start, "replay")
    replay_llm = StructuredLLM(
        ReplayLLM(session.store, session.branch_id), LLMConfig(), Tracer(session.store, LLMConfig())
    )
    run(Simulation(replay, replay_llm, reflect_threshold=1.5, max_active_memories=10).run(12))

    recorded = session.store.events(session.branch_id, after=start)
    replayed = session.store.events(replay.branch_id, after=start)
    assert len(recorded) > 20
    assert comparable(replayed) == comparable(recorded)

    def texts(branch, who):
        return [(m.kind, m.text, m.importance) for m in sim.memory.list(branch, who, include_superseded=True)]

    for who in (toy.ANNA, toy.OTTO, toy.LENA):
        assert texts(replay.branch_id, who) == texts(session.branch_id, who)


def test_the_same_world_diverges_under_different_seeds():
    first, second = toy.build_toy(), toy.build_toy()
    run(offline_sim(first, seed="one")[0].run(10))
    run(offline_sim(second, seed="two")[0].run(10))
    narrations = lambda s: [e.narration for e in s.store.events(s.branch_id, after=7)]
    assert narrations(first) != narrations(second)


def test_simulation_without_a_model_only_advances_time():
    session = toy.build_toy()
    result = run(Simulation(session, None).tick())
    assert {e.actor for e in result.events} == {"system"} and result.outcomes == []
    assert session.state.sim_time == toy.START + timedelta(hours=1)


def test_bare_slugs_and_names_are_resolved_to_ids():
    session = toy.build_toy()
    fake = FakeLLM({"agent.act": {
        "verb": "give", "target": "Otto", "args": {"item": "coin", "quantity": 1},
        "say": {"text": "Here.", "to": ["Otto Brandt"],
                "claims": [{"subject": "otto_brandt", "predicate": "hoards", "value": "grain"}]},
    }})
    session.commit([EventDraft(actor="system", effects=[fx.MoveEntity(entity=toy.OTTO, to=toy.BAKERY)])])
    result = act(session, build_agent(session, fake))
    assert result.ok and len(fake.calls) == 1
    intent = result.intent
    assert intent.target == toy.OTTO and intent.args["item"] == toy.COIN
    assert intent.utterance.addressees == [toy.OTTO]
    assert intent.utterance.claims[0].subject == toy.OTTO


def test_move_by_bare_slug_is_accepted():
    session = toy.build_toy()
    fake = FakeLLM({"agent.act": {"verb": "move", "target": "market_square", "text": "go out"}})
    result = act(session, build_agent(session, fake))
    assert result.ok and result.intent.target == toy.SQUARE
