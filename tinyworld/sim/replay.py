"""Replaying a finished run from its journal and recorded model calls.

A branch's journal lists what drove it: ticks with the step each took, time
skips, god commands, budget changes. Replay runs those again on a new branch
with every model reply served from the recording. If the simulation is
deterministic apart from the model, the two event logs come out identical.
"""

import json
from dataclasses import dataclass

from pydantic import TypeAdapter

from tinyworld.core.events import Event, EventDraft, Intent
from tinyworld.core.session import WorldSession
from tinyworld.core.store import Store
from tinyworld.gm.adjudicator import Adjudicator
from tinyworld.gm.master import GameMaster
from tinyworld.god.channel import GodChannel
from tinyworld.god.parser import GodCommand
from tinyworld.llm.router import LLMConfig
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.trace import ReplayLLM, Tracer
from tinyworld.llm.types import CallContext
from tinyworld.sim.budget import Budget
from tinyworld.sim.clock import advance_world, settle_intents
from tinyworld.sim.loop import Simulation
from tinyworld.sim.step import apply_intents
from tinyworld.sim.timeskip import TimeSkip

_COMMANDS = TypeAdapter(list[GodCommand])
_INTENTS = TypeAdapter(list[Intent])


@dataclass
class ReplayReport:
    source_branch: str
    replay_branch: str
    from_seq: int
    operations: int
    recorded_events: int
    replayed_events: int
    identical: bool
    first_difference: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def comparable(event: Event) -> dict:
    """An event without the fields that legitimately differ between branches."""
    return event.model_dump(mode="json", exclude={"branch_id", "trace_id"})


def _first_difference(recorded: list[Event], replayed: list[Event]) -> str:
    for original, again in zip(recorded, replayed):
        if comparable(original) != comparable(again):
            return (
                f"event {original.seq}: recorded {original.narration!r}, "
                f"replayed {again.narration!r}"
            )
    if len(recorded) != len(replayed):
        return f"recorded {len(recorded)} events, replayed {len(replayed)}"
    return ""


async def replay(
    store: Store,
    source_branch: str,
    config: LLMConfig | None = None,
    *,
    name: str = "replay",
    sim_options: dict | None = None,
) -> ReplayReport:
    """Re-run ``source_branch`` from where its journal starts and compare the logs.

    Makes no model calls: every reply comes from the recording. A reply that
    was never recorded surfaces as a difference, not as an exception.
    """
    config = config or LLMConfig.load()
    journal = store.journal(source_branch)
    row = store.branch(source_branch)
    if row["parent_id"] is not None:
        base_branch, from_seq = row["parent_id"], row["fork_seq"]
    else:
        base_branch = source_branch
        from_seq = journal[0]["seq_before"] if journal else store.head_seq(source_branch)

    session = WorldSession(store, store.fork(base_branch, from_seq, name))
    llm = StructuredLLM(ReplayLLM(store, source_branch), config, Tracer(store, config))
    budget = Budget(store, session.branch_id)
    sim = Simulation(session, llm, budget=budget, **(sim_options or {}))
    if any(r["op"] == "draw" and '"noise.' in r["args_json"] for r in journal):
        # The run's far-off senses were unreliable; read the same slips back.
        from tinyworld.core.entropy import Entropy

        sim.noise = Entropy.replaying(store, source_branch, kinds=("noise.",))
    skipper = TimeSkip(sim)
    god = GodChannel(llm)

    batched: list = []  # observations held back to the end of a window
    for entry in journal:
        args = json.loads(entry["args_json"])
        op = entry["op"]
        if op == "tick":
            await sim.tick(args["step"], journal=False)
        elif op == "skip":
            await skipper.skip(args["minutes"], journal=False)
        elif op == "god":
            await god.submit(session, args["text"], journal=False)
        elif op == "god_apply":
            commands = _COMMANDS.validate_python(args["commands"])
            await god.apply(session, args["text"], commands, journal=False)
        elif op == "remember":
            await sim.remember_events(args["seqs"], args["tick_seq"], journal=False)
        elif op == "promote":
            await sim.promote(args["ids"], reason=args["reason"], journal=False)
        elif op == "budget":
            budget.run_cap = args["run_cap"]
            budget.agent_cap = args["agent_cap"]
        elif op == "clock":
            await advance_world(sim, args["minutes"], args["tick_seq"])
        elif op == "async_intents":
            held, _ = await settle_intents(
                sim, _INTENTS.validate_python(args["intents"]), args["tick_seq"], args.get("causes"),
                remember=False, scenes=args.get("scenes", True),
            )
            batched.extend(held.observations)
        elif op == "window_end":
            if batched and not args.get("drop"):
                await sim.remember(batched, args["tick_seq"])
            batched = []
        elif op == "drafts":
            drafts = [EventDraft.model_validate(d) for d in args["drafts"]]
            events = session.commit(drafts, atomic=False).events
            if events and args.get("notes"):
                sim.write_notes([tuple(n) for n in args["notes"]], events[-1].seq, 0.8)
            if events and args.get("beliefs"):
                from tinyworld.sim.town import write_beliefs

                write_beliefs(sim, [tuple(b) for b in args["beliefs"]])
        elif op == "town_intents":
            gm = GameMaster(Adjudicator(llm), seed=session.world_id)
            step = await apply_intents(
                session, gm, _INTENTS.validate_python(args["intents"]),
                CallContext(session.branch_id, args["tick_seq"]),
            )
            await sim.remember(step.observations, args["tick_seq"])
        elif op == "intents":
            gm = GameMaster(Adjudicator(llm), seed=session.world_id)
            await apply_intents(session, gm, _INTENTS.validate_python(args["intents"]))

    recorded = store.events(source_branch, after=from_seq)
    replayed = store.events(session.branch_id, after=from_seq)
    difference = _first_difference(recorded, replayed)
    return ReplayReport(
        source_branch=source_branch,
        replay_branch=session.branch_id,
        from_seq=from_seq,
        operations=len(journal),
        recorded_events=len(recorded),
        replayed_events=len(replayed),
        identical=not difference,
        first_difference=difference,
    )
