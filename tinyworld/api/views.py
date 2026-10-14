"""Read-only views of a branch for the API: agents, diffs, chronicle, export."""

import json

from tinyworld.agents.beliefs import compare_beliefs
from tinyworld.agents.persona import persona_of
from tinyworld.api.runner import BranchRunner, event_json
from tinyworld.core import branches
from tinyworld.core import effects as fx
from tinyworld.core.state import WorldState
from tinyworld.core.store import Store
from tinyworld.gm.context import name_of
from tinyworld.llm import ledger


def _memory_json(memory) -> dict:
    return {
        "id": memory.id,
        "kind": memory.kind,
        "text": memory.text,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "sim_time": memory.sim_time.isoformat(),
        "created_seq": memory.created_seq,
    }


def people_view(state: WorldState) -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "alive": p.alive,
            "location": p.location,
            "tier": p.attrs.get("tier", 0),
            "occupation": p.attrs.get("occupation", ""),
            "age": p.attrs.get("age"),
            "has_persona": persona_of(p) is not None,
        }
        for p in sorted(state.people(alive=False), key=lambda p: p.name)
    ]


def last_thought(store: Store, branch_id: str, agent_id: str) -> str:
    clause, params = store.lineage_clause(branch_id, "tick_seq", before=True)
    rows = store.query(
        f"SELECT response_json FROM llm_calls WHERE {clause} AND agent=?"
        " AND role LIKE 'agent.act%' ORDER BY tick_seq DESC, ordinal DESC LIMIT 1",
        params + [agent_id],
    )
    if not rows:
        return ""
    try:
        reply = json.loads(json.loads(rows[0]["response_json"])["text"])
    except (ValueError, KeyError, TypeError):
        return ""
    return reply.get("thought", "") if isinstance(reply, dict) else ""


def agent_view(runner: BranchRunner, agent_id: str) -> dict | None:
    session = runner.session
    state = session.state
    entity = state.entities.get(agent_id)
    if entity is None or entity.kind != "person":
        return None
    sim = runner.sim
    branch = session.branch_id
    persona = persona_of(entity)
    memories = sim.memory.list(branch, agent_id)
    recent = sorted(memories, key=lambda m: m.created_seq, reverse=True)[:15]
    weighty = sorted(memories, key=lambda m: (m.importance, m.created_seq), reverse=True)[:6]
    comparisons = compare_beliefs(state, sim.beliefs.current(branch, agent_id))
    relations = [
        {
            "other": other.id,
            "name": other.name,
            "theirs": relation.model_dump() if (relation := state.relation(agent_id, other.id)) else None,
            "towards": back.model_dump() if (back := state.relation(other.id, agent_id)) else None,
        }
        for other in state.people(alive=False)
        if other.id != agent_id
        and (state.relation(agent_id, other.id) or state.relation(other.id, agent_id))
    ]
    return {
        "id": entity.id,
        "name": entity.name,
        "alive": entity.alive,
        "location": entity.location,
        "location_name": name_of(state, entity.location),
        "attrs": {k: v for k, v in entity.attrs.items() if k != "persona"},
        "persona": persona.model_dump() if persona else None,
        "inventory": [
            {"id": item, "name": name_of(state, item), "quantity": quantity}
            for item, quantity in sorted(entity.inventory.items())
        ],
        "relations": relations,
        "beliefs": [
            {**c.model_dump(), "source_name": name_of(state, c.source) if c.source else None}
            for c in comparisons
        ],
        "memories": {
            "count": len(memories),
            "recent": [_memory_json(m) for m in recent],
            "important": [_memory_json(m) for m in weighty],
        },
        "plan": sim.planner.current(branch, agent_id),
        "thought": runner.thoughts.get(agent_id) or last_thought(session.store, branch, agent_id),
        "cost": ledger.agent_cost(session.store, branch, agent_id),
    }


def chronicle_view(store: Store, branch_id: str) -> list[dict]:
    """History worth reading back, grouped by year."""
    years: dict[int, list[dict]] = {}
    for event in store.events(branch_id):
        skipped = event.kind == "system" and any(
            isinstance(e, fx.AdvanceTime) for e in event.effects
        ) and event.narration
        if event.kind in ("chronicle", "god") or skipped:
            years.setdefault(event.sim_time.year, []).append(
                {
                    "seq": event.seq,
                    "sim_time": event.sim_time.isoformat(),
                    "kind": "period" if skipped else event.kind,
                    "narration": event.narration,
                }
            )
    return [{"year": year, "entries": entries} for year, entries in sorted(years.items())]


def _people_state(state: WorldState) -> dict[str, dict]:
    return {
        p.id: {"name": p.name, "alive": p.alive, "location": name_of(state, p.location)}
        for p in state.people(alive=False)
    }


def diff_view(store: Store, first: str, second: str) -> dict:
    """What differs between two branches of one world."""
    split, left, right = branches.diverging_events(store, first, second)
    state_a = store.state_at(first)
    state_b = store.state_at(second)
    people_a, people_b = _people_state(state_a), _people_state(state_b)
    people = []
    for person_id in sorted(set(people_a) | set(people_b)):
        a, b = people_a.get(person_id), people_b.get(person_id)
        if a != b:
            people.append({"id": person_id, "name": (a or b)["name"], "a": a, "b": b})
    facts_a = {f.id: f.text for f in state_a.active_facts()}
    facts_b = {f.id: f.text for f in state_b.active_facts()}
    processes = []
    for process_id in sorted(set(state_a.processes) | set(state_b.processes)):
        a, b = state_a.processes.get(process_id), state_b.processes.get(process_id)
        summary = lambda p: None if p is None else {"status": p.status, "progress": p.progress}
        if summary(a) != summary(b):
            processes.append(
                {"id": process_id, "name": (a or b).name, "a": summary(a), "b": summary(b)}
            )

    def told(events):
        return [
            {"seq": e.seq, "sim_time": e.sim_time.isoformat(), "kind": e.kind, "narration": e.narration}
            for e in events
            if e.narration and e.actor != "system"
        ]

    return {
        "split_seq": split,
        "a": {"branch_id": first, "sim_time": state_a.sim_time.isoformat(), "events": told(left)},
        "b": {"branch_id": second, "sim_time": state_b.sim_time.isoformat(), "events": told(right)},
        "people": people,
        "facts_only_a": [facts_a[k] for k in sorted(set(facts_a) - set(facts_b))],
        "facts_only_b": [facts_b[k] for k in sorted(set(facts_b) - set(facts_a))],
        "processes": processes,
    }


def export_view(store: Store, branch_id: str, bible: dict) -> dict:
    branch = store.branch(branch_id)
    world = store.world(branch["world_id"])
    return {
        "world": {"id": world["id"], "premise": world["premise"]},
        "branch": {"id": branch_id, "name": branch["name"], "parent_id": branch["parent_id"]},
        "bible": bible,
        "chronicle": chronicle_view(store, branch_id),
        "events": [event_json(e) for e in store.events(branch_id)],
    }
