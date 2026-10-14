"""Numbers that describe a branch: population, groups, stocks, cost."""

from tinyworld.core.state import WorldState
from tinyworld.core.store import Store
from tinyworld.llm import ledger

MINUTES_PER_YEAR = 365 * 24 * 60


def simulated_years(store: Store, branch_id: str, state: WorldState) -> float:
    start = store.initial_state(branch_id).sim_time
    return (state.sim_time - start).total_seconds() / 60 / MINUTES_PER_YEAR


def cost_per_simulated_year(store: Store, branch_id: str, state: WorldState) -> float | None:
    """Model spend divided by simulated time. None before any time has passed."""
    years = simulated_years(store, branch_id, state)
    if years <= 0:
        return None
    return ledger.total(store, branch_id).cost / years


def world_metrics(store: Store, branch_id: str, state: WorldState) -> dict:
    people = state.people(alive=False)
    tiers: dict[str, int] = {}
    for person in people:
        if person.alive:
            tier = str(person.attrs.get("tier", 0))
            tiers[tier] = tiers.get(tier, 0) + 1

    resources: dict[str, int] = {}
    for entity in state.entities.values():
        for item, quantity in entity.inventory.items():
            resources[item] = resources.get(item, 0) + quantity

    background = state.rules.get("population")
    background_total = (
        sum(g.get("count", 0) for g in background if isinstance(g, dict))
        if isinstance(background, list)
        else 0
    )

    usage = ledger.total(store, branch_id)
    return {
        "sim_time": state.sim_time.isoformat(),
        "seq": state.seq,
        "simulated_years": round(simulated_years(store, branch_id, state), 4),
        "population": {
            "alive": sum(1 for p in people if p.alive),
            "dead": sum(1 for p in people if not p.alive),
            "by_tier": tiers,
            "background": background_total,
        },
        "groups": [
            {
                "id": e.id,
                "name": e.name,
                "kind": e.kind,
                "morale": e.attrs.get("morale"),
                "influence": e.attrs.get("influence"),
                "members": e.attrs.get("members"),
            }
            for e in sorted(state.entities.values(), key=lambda e: e.id)
            if e.kind in ("faction", "org")
        ],
        "resources": [
            {"id": item, "name": state.entities[item].name, "total": total}
            for item, total in sorted(resources.items())
            if item in state.entities
        ],
        "processes": [
            {
                "id": p.id, "name": p.name, "owner": p.owner,
                "progress": p.progress, "status": p.status,
            }
            for p in state.processes.values()
        ],
        "facts": len(state.active_facts()),
        "cost": {
            "total": usage.cost,
            "calls": usage.calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "by_tier": {k: v.cost for k, v in ledger.by(store, branch_id, "tier").items()},
            "by_role": {k: v.cost for k, v in ledger.by(store, branch_id, "role").items()},
            "per_simulated_year": cost_per_simulated_year(store, branch_id, state),
        },
    }
