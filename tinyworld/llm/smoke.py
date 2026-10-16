"""Try a real model on the prompts the application actually sends.

    python -m tinyworld.llm.smoke --provider gemini
    python -m tinyworld.llm.smoke --prompt "Name three causes of the Thirty Years War"
    python -m tinyworld.llm.smoke --list-models

Each step builds the real prompt and the real schema, calls the model, and
reports whether the reply passed validation, how many attempts it took, and
what it cost in tokens. A step that needed repairs still passes, but says so:
a model that only works on the third try is a model you will pay triple for.
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass

from pydantic import BaseModel

from tinyworld.agents.persona import persona_of
from tinyworld.api.hub import chosen_provider, make_client
from tinyworld.core.events import Intent, Verb
from tinyworld.core.session import WorldSession
from tinyworld.fixtures import berlin, toy
from tinyworld.genesis.pipeline import GenesisPipeline
from tinyworld.god.channel import GodChannel
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import Tracer
from tinyworld.llm.types import CallContext
from tinyworld.sim.loop import Simulation

STEPS = ["prompt", "agent", "gm", "god", "genesis"]


class Answer(BaseModel):
    answer: str


@dataclass
class Result:
    step: str
    ok: bool
    detail: str
    seconds: float
    calls: int
    repairs: int
    tokens_in: int
    tokens_out: int


def _load_dotenv(path: str = ".env") -> None:
    """Read KEY=VALUE lines into the environment without overriding it."""
    import os
    from pathlib import Path

    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _tally(session: WorldSession, before: int) -> tuple[int, int, int, int]:
    """(calls, repairs, tokens in, tokens out) recorded since ``before`` calls."""
    # Every branch: genesis records its calls under its own pseudo-branch.
    rows = session.store.query(
        "SELECT branch_id, role, agent, tick_seq, input_tokens, output_tokens"
        " FROM llm_calls ORDER BY rowid"
    )[before:]
    calls = len(rows)
    distinct = len({(r["branch_id"], r["role"], r["agent"], r["tick_seq"]) for r in rows})
    return (
        calls,
        calls - distinct,
        sum(r["input_tokens"] for r in rows),
        sum(r["output_tokens"] for r in rows),
    )


async def run_steps(
    llm: StructuredLLM, session: WorldSession, steps: list[str], prompt: str, premise: str
) -> list[Result]:
    results: list[Result] = []
    branch = session.branch_id

    async def step(name: str, body) -> None:
        before = len(session.store.query("SELECT 1 FROM llm_calls"))
        started = time.monotonic()
        try:
            ok, detail = await body()
        except Exception as exc:  # a step failing must not stop the others
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        calls, repairs, tin, tout = _tally(session, before)
        if ok and calls == 0:
            ok, detail = False, "no model call was made"
        results.append(
            Result(name, ok, detail, time.monotonic() - started, calls, repairs, tin, tout)
        )

    async def free_prompt():
        reply = await llm.call(
            "smoke.free", Answer,
            system="Answer the question briefly and accurately.",
            user=prompt,
            context=CallContext(branch, 0, "smoke"),
            fallback=Answer(answer=""),
            max_tokens=800,
        )
        if not reply.ok:
            return False, f"no valid reply: {reply.error[:200]}"
        return True, reply.value.answer.strip().replace("\n", " ")[:300]

    async def agent():
        sim = Simulation(session, llm)
        lines, failed = [], 0
        for person in sim.active_agents(session.state, 0):
            acted = await sim.agent.act(
                session.state, person, branch, CallContext(branch, 1, person.id), -1
            )
            failed += not acted.ok
            lines.append(
                f"{person.name}: {acted.intent.verb.value}"
                f"{' ' + acted.intent.target if acted.intent.target else ''}"
                f"{' (fell back)' if not acted.ok else ''}"
            )
        return failed == 0, "; ".join(lines)

    async def game_master():
        sim = Simulation(session, llm)
        intent = Intent(
            agent=toy.ANNA, verb=Verb.OTHER,
            text="try to calm the queue outside her shop with a joke",
        )
        resolution = await sim.gm.resolve(session.state, [intent], CallContext(branch, 2))
        outcome = resolution.outcomes[0]
        ok = outcome.status != "failed" or "could not resolve" not in outcome.reason
        return ok, f"{outcome.status}: {outcome.narration or outcome.reason}"[:300]

    async def god():
        channel = GodChannel(llm, world_digest="A small town under rationing, spring 1943.")
        result = await channel.submit(session, "A storm tears the roof off the Golden Stag tavern")
        return (
            result.verdict in ("apply", "apply_adjusted"),
            f"{result.verdict}: {result.explanation or result.question}"[:300],
        )

    async def genesis():
        pipeline = GenesisPipeline(session.store, llm)
        world = pipeline.create_world(premise)
        parsed = await pipeline.stage_premise(world)
        if parsed.questions:
            return True, f"asked: {parsed.questions[0]}"
        return bool(parsed.start_date), (
            f"{parsed.start_date}; {parsed.place[:80]}; diverges: {parsed.divergence_point[:80]}"
        )

    table = {"prompt": free_prompt, "agent": agent, "gm": game_master, "god": god, "genesis": genesis}
    for name in steps:
        await step(name, table[name])
    return results


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", choices=["gemini", "anthropic", "openrouter", "local"], default=None)
    parser.add_argument("--prompt", default="In one sentence, what was the Molotov-Ribbentrop Pact?")
    parser.add_argument("--premise", default=berlin.PREMISE_TEXT)
    parser.add_argument("--only", nargs="+", choices=STEPS, help="run just these steps")
    parser.add_argument("--list-models", action="store_true")
    options = parser.parse_args(argv)

    _load_dotenv()
    provider = options.provider or chosen_provider()
    if provider is None:
        print("No API key found. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY), or put it in .env.")
        return 2
    client = make_client(provider)
    if client is None:
        print(f"Could not create a {provider} client. Is its key set, and its package installed?")
        return 2

    if options.list_models:
        if not hasattr(client, "list_models"):
            print(f"Listing models is only implemented for gemini, not {provider}.")
            return 2
        for model in await client.list_models():
            print(f"{model['id']:<40} in {model['input_limit']}  out {model['output_limit']}")
        return 0

    config = LLMConfig.load(provider=provider)
    print(f"provider: {provider}")
    print("models:   " + ", ".join(f"{t}={m}" for t, m in config.tiers.items()))

    session = toy.build_toy()
    llm = StructuredLLM(client, config, Tracer(session.store, config))
    steps = options.only or STEPS
    results = await run_steps(llm, session, steps, options.prompt, options.premise)

    print()
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        repairs = f", {r.repairs} repair(s)" if r.repairs else ""
        print(f"[{mark}] {r.step:<8} {r.seconds:5.1f}s  {r.calls} call(s){repairs}, "
              f"{r.tokens_in} in / {r.tokens_out} out")
        print(f"         {r.detail}")
    print(
        f"\ntotal: {sum(r.calls for r in results)} calls, "
        f"{sum(r.tokens_in for r in results)} in / {sum(r.tokens_out for r in results)} out tokens"
    )
    failed = [r.step for r in results if not r.ok]
    print("all steps passed" if not failed else f"failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
