"""A run report: what the agents actually did, and why attempts failed.

Built only from the stored log and the model-call ledger, so it works on any
branch after the fact. The point is to see problems that a green test suite
cannot: a world where everyone waits, repeats themselves, or keeps failing.
"""

import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field

from tinyworld.core import effects as fx
from tinyworld.core.events import Event
from tinyworld.core.state import WorldState
from tinyworld.core.store import Store
from tinyworld.llm import ledger

# A failure message is "<name> could not do this (...): reason" or
# "<name> tried (...) and it did not work: reason". Tags are checked in order.
FAILURE_TAGS: list[tuple[str, re.Pattern]] = [
    ("unreachable", re.compile(r"no way to|no route", re.I)),
    ("unknown_id", re.compile(r"no such|there is no|not a place|not a person|unknown", re.I)),
    ("out_of_reach", re.compile(r"not here|not within reach|not present|too far", re.I)),
    ("blocked", re.compile(r"needs |requires|is no longer|work is at|does not have", re.I)),
    ("no_target", re.compile(r"nobody|nothing to say|cannot be done|cannot give|already", re.I)),
    ("provider", re.compile(r"no game master model|rate limit|connection", re.I)),
]
_FAILED = re.compile(r"could not do this|did not work|only partly managed")

ACTION_KINDS = ("move", "speak", "work", "give", "take", "wait", "rest", "other")


def failure_tag(text: str) -> str:
    reason = text.split(":", 1)[1] if ":" in text else text
    for tag, pattern in FAILURE_TAGS:
        if pattern.search(reason):
            return tag
    return "other"


def classify(event: Event) -> str:
    """The kind of action an event records, from what it did."""
    for effect in event.effects:
        if isinstance(effect, fx.MoveEntity):
            return "move"
        if isinstance(effect, fx.AdvanceProcess):
            return "work"
        if isinstance(effect, fx.TransferItem):
            return "give" if " gives " in event.narration or " leaves " in event.narration else "take"
    if any(isinstance(e, fx.Utter) for e in event.effects):
        return "speak"
    text = event.narration
    if " waits" in text:
        return "wait"
    if " rests" in text or " sleeps" in text:
        return "rest"
    if " works " in text:
        return "work"
    return "other"


_DIGITS = re.compile(r"\d+")


def _signature(event: Event) -> str:
    return f"{classify(event)}|{_DIGITS.sub('#', event.narration)}"


@dataclass
class AgentLine:
    id: str
    name: str
    actions: int = 0
    mix: dict[str, int] = field(default_factory=dict)
    failures: int = 0
    repeats: int = 0


@dataclass
class RunReport:
    branch_id: str
    simulated_hours: float
    events: int
    decisions: int
    mix: dict[str, int]
    wait_share: float
    repetition_share: float
    failures: dict[str, int]
    failure_samples: list[str]
    model_calls: dict[str, int]
    total_calls: int
    tokens: int
    cost: float
    routine_share: float
    calls_per_sim_day: float | None
    agents: list[AgentLine]
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _repeats(events: list[Event], run: int = 3) -> set[int]:
    """Seq numbers of events that finish a run of ``run`` identical actions."""
    flagged: set[int] = set()
    count, previous = 0, None
    for event in events:
        signature = _signature(event)
        count = count + 1 if signature == previous else 1
        previous = signature
        if count >= run:
            flagged.add(event.seq)
    return flagged


def _memory_failures(store: Store, branch_id: str) -> list[str]:
    clause, params = store.lineage_clause(branch_id, "created_seq")
    rows = store.query(
        f"SELECT text FROM memories WHERE {clause} AND confidence>=1.0"
        " AND (text LIKE '%could not do this%' OR text LIKE '%did not work%'"
        " OR text LIKE '%only partly managed%') ORDER BY created_seq",
        params,
    )
    return [row["text"] for row in rows if _FAILED.search(row["text"])]


def _llm_calls(store: Store, branch_id: str) -> tuple[dict[str, int], int]:
    clause, params = store.lineage_clause(branch_id, "tick_seq", before=True)
    try:
        rows = store.query(
            f"SELECT role, COUNT(*) AS n FROM llm_calls WHERE {clause} GROUP BY role",
            params,
        )
    except sqlite3.Error:
        return {}, 0
    by_role = {row["role"]: row["n"] for row in rows}
    return by_role, sum(by_role.values())


def build_report(store: Store, branch_id: str, state: WorldState) -> RunReport:
    start = store.initial_state(branch_id).sim_time
    hours = max(0.0, (state.sim_time - start).total_seconds() / 3600)
    events = store.events(branch_id)
    person_actions = [
        e for e in events
        if e.kind in ("action", "utterance") and e.actor in state.entities
        and state.entities[e.actor].kind == "person"
    ]
    mix: Counter = Counter(classify(e) for e in person_actions)
    flagged = _repeats(person_actions)

    lines: dict[str, AgentLine] = {}
    by_actor: dict[str, list[Event]] = {}
    for event in person_actions:
        by_actor.setdefault(event.actor, []).append(event)
    for actor, items in sorted(by_actor.items()):
        line = AgentLine(actor, state.entities[actor].name, actions=len(items))
        line.mix = dict(Counter(classify(e) for e in items))
        line.repeats = len(_repeats(items))
        lines[actor] = line

    failure_texts = _memory_failures(store, branch_id)
    failures = Counter(failure_tag(text) for text in failure_texts)
    for text in failure_texts:
        for line in lines.values():
            if text.startswith(line.name):
                line.failures += 1
                break

    by_role, total_calls = _llm_calls(store, branch_id)
    usage = ledger.total(store, branch_id)
    acting = sum(n for role, n in by_role.items() if role.startswith("agent.act"))
    decisions = len(person_actions)
    routine_share = (
        round(max(0.0, 1 - acting / decisions), 3) if decisions else 0.0
    )
    days = hours / 24
    wait_share = round(mix.get("wait", 0) / decisions, 3) if decisions else 0.0
    repetition_share = round(len(flagged) / decisions, 3) if decisions else 0.0

    warnings: list[str] = []
    if decisions >= 10 and wait_share > 0.4:
        warnings.append(f"{round(wait_share * 100)}% of actions are waiting: little is driving the agents")
    if decisions >= 10 and repetition_share > 0.15:
        warnings.append(f"{round(repetition_share * 100)}% of actions repeat the same thing")
    attempts = decisions + sum(failures.values())
    if attempts >= 10 and sum(failures.values()) / attempts > 0.3:
        top = failures.most_common(1)[0][0]
        warnings.append(f"{round(sum(failures.values()) / attempts * 100)}% of attempts fail, mostly '{top}'")
    if decisions >= 10 and not mix.get("speak"):
        warnings.append("nobody speaks")

    return RunReport(
        branch_id=branch_id,
        simulated_hours=round(hours, 2),
        events=len(events),
        decisions=decisions,
        mix={kind: mix.get(kind, 0) for kind in ACTION_KINDS if mix.get(kind)},
        wait_share=wait_share,
        repetition_share=repetition_share,
        failures=dict(failures),
        failure_samples=failure_texts[:5],
        model_calls=by_role,
        total_calls=total_calls,
        tokens=usage.input_tokens + usage.output_tokens,
        cost=round(usage.cost, 4),
        routine_share=routine_share,
        calls_per_sim_day=round(total_calls / days, 1) if days > 0 else None,
        agents=list(lines.values()),
        warnings=warnings,
    )


def format_report(report: RunReport) -> str:
    out = [
        f"simulated {report.simulated_hours} h, {report.events} events, "
        f"{report.decisions} actions",
        "actions: " + (", ".join(f"{k} {v}" for k, v in report.mix.items()) or "none"),
        f"wait {round(report.wait_share * 100)}%  repeats {round(report.repetition_share * 100)}%  "
        f"routine {round(report.routine_share * 100)}%",
        f"model calls {report.total_calls}"
        + (f" ({report.calls_per_sim_day}/sim day)" if report.calls_per_sim_day else "")
        + f", {report.tokens} tokens, cost {report.cost}",
    ]
    if report.failures:
        out.append("failures: " + ", ".join(f"{k} {v}" for k, v in sorted(report.failures.items())))
    for text in report.failure_samples[:3]:
        out.append("  - " + text)
    for warning in report.warnings:
        out.append("WARNING: " + warning)
    return "\n".join(out)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Report on a stored branch")
    parser.add_argument("--db", required=True)
    parser.add_argument("--branch", help="branch id; defaults to the first one")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    store = Store(args.db)
    branch = args.branch
    if branch is None:
        world = store.worlds()[0]
        branch = store.branches(world["id"])[0]["id"]
    state = store.state_at(branch)
    report = build_report(store, branch, state)
    print(json.dumps(report.to_dict(), indent=2) if args.json else format_report(report))


if __name__ == "__main__":
    main()
