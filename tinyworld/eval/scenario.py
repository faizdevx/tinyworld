"""Run the whole application on one premise with a real model and report on it.

    python -m tinyworld.eval.scenario --premise "What if ... " --ticks 2 --skip 6mo

It runs genesis (research, bible, review), seeds a world, lets the people act
for a few steps, makes two god interventions, skips time, then checks the
result: invariants, anachronisms, persona judging, and a replay from the
recording. Calls go to whatever provider has a key set.
"""

import argparse
import asyncio
import sys
import time

from tinyworld.api.hub import chosen_provider, default_search, make_client
from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.core.time import parse_step
from tinyworld.eval import anachronism, invariants, judge
from tinyworld.eval.metrics import world_metrics
from tinyworld.genesis import seeding
from tinyworld.genesis.pipeline import GenesisPipeline
from tinyworld.god.channel import GodChannel
from tinyworld.llm import ledger
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.smoke import _load_dotenv
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.sim.loop import Simulation
from tinyworld.sim.replay import replay
from tinyworld.sim.scheduler import StepPolicy
from tinyworld.sim.timeskip import TimeSkip, label

STORM = "A fierce storm knocks out electricity across the city for three days"
NEWCOMER = (
    "A young woman named Zoya Siddiqui arrives in the city from a small town "
    "and starts working for a shopkeeper"
)


class Counting:
    """Counts the calls that actually reach the provider."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls = 0

    async def complete(self, request, model, effort):
        self.calls += 1
        return await self.inner.complete(request, model, effort)


def say(text: str = "") -> None:
    print(text, flush=True)


def heading(text: str) -> None:
    say(f"\n== {text} " + "=" * max(0, 70 - len(text)))


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--premise", required=True)
    parser.add_argument("--provider", choices=["gemini", "anthropic", "openrouter"], default=None)
    parser.add_argument("--ticks", type=int, default=2)
    parser.add_argument("--skip", default="6mo", help="how far to skip, e.g. 6mo, 2y")
    parser.add_argument("--judge", type=int, default=3, help="people to judge (0 to skip)")
    parser.add_argument("--no-research", action="store_true")
    parser.add_argument("--db", default=":memory:", help="keep the world in this SQLite file")
    options = parser.parse_args(argv)

    _load_dotenv()
    provider = options.provider or chosen_provider()
    client = make_client(provider)
    if client is None:
        say("No usable API key. Set GEMINI_API_KEY or ANTHROPIC_API_KEY.")
        return 2
    config = LLMConfig.load(provider=provider)
    store = Store(options.db)
    tracer = Tracer(store, config)
    client = Counting(client)
    llm = StructuredLLM(client, config, tracer)
    started = time.monotonic()
    problems: list[str] = []

    say(f"provider {provider}; " + ", ".join(f"{t}={m}" for t, m in config.tiers.items()))
    say(f"premise: {options.premise}")

    # -- genesis ----------------------------------------------------------
    heading("Genesis")
    search = default_search(not options.no_research)
    pipeline = GenesisPipeline(
        store, llm, search=search,
        on_progress=lambda stage, detail: say(f"  [{stage}] {detail}"),
    )
    world_id = pipeline.create_world(options.premise)
    status = await pipeline.run(world_id)
    if status.questions:
        say("The premise needs answers before it can be built:")
        for question in status.questions:
            say(f"  - {question}")
        return 1
    bible = pipeline.bibles.load(world_id)
    say(f"\nwhen/where: {bible.premise.start_date}, {bible.premise.place}")
    say(f"divergence: {bible.premise.divergence_point}")
    if bible.divergence:
        say(f"\n{bible.divergence.summary}")
        for consequence in bible.divergence.consequences[:6]:
            say(f"  order {consequence.order} ({consequence.confidence:.0%}): {consequence.text}")
    say(
        f"\nbible: {len(bible.geography.places)} places, {len(bible.figures.figures)} people, "
        f"{len(bible.factions.factions)} factions, {len(bible.politics.institutions)} institutions, "
        f"{len(bible.economy.resources)} resources, {len(bible.tensions.tensions)} tensions, "
        f"{len(pipeline.researcher.sources(world_id))} sources"
    )
    for figure in bible.figures.figures:
        say(f"  {figure.name}, {figure.age}, {figure.occupation} — wants: {'; '.join(figure.goals[:1])}")
    blocking = [f for f in status.findings if f.blocking]
    say(f"\nreviewer: {len(status.findings)} finding(s), {len(blocking)} blocking")
    for finding in status.findings[:8]:
        say(f"  ({finding.kind}, {finding.section}) {finding.text}")
    if bible.digest:
        say(f"\ndigest: {bible.digest.overview}")

    # -- seed -------------------------------------------------------------
    heading("Seeding")
    session, notes = pipeline.seed(world_id)
    state_problems = seeding.check_world(session.state)
    say(f"{len(session.state.people())} people, "
        f"{sum(1 for e in session.state.entities.values() if e.kind == 'place')} places, "
        f"{len(session.state.edges)} links; starts {session.state.sim_time:%d %B %Y}")
    for note in notes:
        say(f"  repaired: {note.text}")
    if state_problems:
        problems += [f"seeding: {p}" for p in state_problems]

    digest = bible.world_digest()
    sim = Simulation(session, llm, world_digest=digest, policy=StepPolicy())
    god = GodChannel(llm, world_digest=digest)
    first_seq = session.state.seq

    # -- running ----------------------------------------------------------
    heading(f"Running {options.ticks} step(s)")
    for index in range(options.ticks):
        result = await sim.tick()
        say(f"step {index + 1}: {session.state.sim_time:%d %b %Y %H:%M}, "
            f"{len(result.events)} events, {result.memories_written} memories, "
            f"{result.reflections} reflections")
        for event in result.events:
            if event.narration and event.actor.startswith("person:"):
                say(f"   {event.narration}")
        for agent_id, thought in result.thoughts.items():
            if thought:
                name = session.state.entities[agent_id].name
                say(f"   ({name} thinks: {thought[:140]})")
    decisions = session.store.query(
        "SELECT COUNT(*) AS n FROM llm_calls WHERE branch_id=? AND role LIKE 'agent.act%'",
        (session.branch_id,),
    )[0]["n"]
    say(f"agent decision calls so far: {decisions}")

    # -- god --------------------------------------------------------------
    heading("The god intervenes")
    for text in (STORM, NEWCOMER):
        before = session.state.seq
        result = await god.submit(session, text)
        say(f'"{text}"\n  -> {result.verdict}: {(result.explanation or result.question)[:260]}')
        if result.applied:
            targets = [j.command.target for j in result.judgements if j.command.target.startswith("person:")]
            await sim.promote(targets, reason="touched by the god", journal=True)
            await sim.remember_events(result.event_seqs, before)
        else:
            problems.append(f"god command not applied: {text!r}: {result.explanation or result.question}")
    await sim.tick()

    # -- time -------------------------------------------------------------
    heading(f"Skipping {options.skip}")
    skip = await TimeSkip(sim).skip(parse_step(options.skip))
    say(f"{skip.periods} period(s) chronicled, {len(skip.rejected)} proposed event(s) ruled out, "
        f"now {session.state.sim_time:%d %B %Y}")
    for summary in skip.summaries[:8]:
        say(f"  {summary}")
    for narration, reason in skip.rejected[:5]:
        say(f"  ruled out: {narration[:90]} — {reason}")
    chronicled = [e for e in session.store.events(session.branch_id, kind="chronicle")]
    say(f"\nwhat the chronicler recorded ({len(chronicled)}):")
    for event in chronicled[:12]:
        say(f"  {event.sim_time:%b %Y}: {event.narration}")
    if not skip.complete:
        problems.append(f"skip stopped early: {skip.stopped}")

    # -- checks -----------------------------------------------------------
    heading("Checks")
    violations = invariants.check_log(session.store, session.branch_id)
    say(f"invariants: {'hold' if not violations else f'{len(violations)} broken'}")
    for violation in violations[:5]:
        say(f"  {violation}")
    problems += [str(v) for v in violations]

    found = anachronism.scan(session.store, session.branch_id, session.state)
    leaks = anachronism.leaks(found)
    say(f"anachronisms: {len(found)} found, {len(leaks)} not asked for by the god")
    for item in found[:6]:
        say(f"  event {item.seq} ({item.where}{', god' if item.by_god else ''}): "
            f"\"{item.term}\" in {item.text[:90]!r}")

    metrics = world_metrics(session.store, session.branch_id, session.state)
    say(f"people: {metrics['population']['alive']} alive, {metrics['population']['dead']} dead")
    for group in metrics["groups"][:6]:
        say(f"  {group['name']}: morale {group['morale']}, influence {group['influence']}")

    if options.judge > 0:
        verdicts = await judge.judge_agents(
            llm, session.store, session.branch_id, session.state, sample=options.judge
        )
        summary = judge.summary(verdicts)
        say(f"persona judging: {summary}")
        for item in verdicts:
            if item.verdict:
                say(f"  {item.name}: consistency {item.verdict.consistency}, voice {item.verdict.voice}, "
                    f"distinct {item.verdict.distinctness}; {item.verdict.notes[:140]}")
                for leak in item.verdict.knowledge_leaks[:2]:
                    say(f"    knowledge leak: {leak[:120]}")

    heading("Replay (no model calls)")
    calls_before = client.calls
    report = await replay(
        store, session.branch_id, config,
        sim_options={"world_digest": digest, "policy": StepPolicy()},
    )
    made = client.calls - calls_before
    say(f"{report.operations} step(s) replayed: {report.replayed_events} events vs "
        f"{report.recorded_events} recorded — {'identical' if report.identical else 'DIFFERENT'}")
    if not report.identical:
        say(f"  {report.first_difference}")
        problems.append(f"replay differs: {report.first_difference}")
    say(f"calls that reached the provider during replay: {made}")
    if made:
        problems.append(f"replay called the provider {made} time(s)")

    # -- totals -----------------------------------------------------------
    heading("Totals")
    own = ledger.total(store, session.branch_id, own_only=True)
    gen = ledger.total(store, f"genesis:{world_id}", own_only=True)
    say(f"calls: {own.calls + gen.calls} "
        f"(genesis {gen.calls}, simulation {own.calls}), "
        f"tokens in/out: {own.input_tokens + gen.input_tokens}/{own.output_tokens + gen.output_tokens}")
    by_role = ledger.by(store, session.branch_id, "role", own_only=True)
    say("simulation calls by role: " + ", ".join(f"{k}={v.calls}" for k, v in sorted(by_role.items())))
    say(f"provider requests made in total: {client.calls}")
    say(f"events: {session.state.seq - first_seq} after seeding; "
        f"skipped {label(parse_step(options.skip))}; wall time {time.monotonic() - started:.0f}s")
    say("\nPROBLEMS: " + ("none" if not problems else ""))
    for problem in problems:
        say(f"  - {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
