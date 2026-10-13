"""Token and cost accounting over recorded calls."""

from dataclasses import dataclass

from tinyworld.core.store import Store

_GROUPS = {"role", "agent", "tier", "model"}


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


def _where(store: Store, branch_id: str, own_only: bool) -> tuple[str, list]:
    if own_only:
        return "branch_id=?", [branch_id]
    return store.lineage_clause(branch_id, "tick_seq", before=True)


def total(store: Store, branch_id: str, *, own_only: bool = False) -> Usage:
    """Usage visible from a branch. ``own_only`` excludes inherited ancestor calls."""
    clause, params = _where(store, branch_id, own_only)
    row = store.query(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens,"
        " COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(cost),0) AS cost"
        f" FROM llm_calls WHERE {clause}",
        params,
    )[0]
    return Usage(row["calls"], row["input_tokens"], row["output_tokens"], row["cost"])


def by(
    store: Store, branch_id: str, group: str, *, own_only: bool = False
) -> dict[str, Usage]:
    if group not in _GROUPS:
        raise ValueError(f"cannot group by {group!r}")
    clause, params = _where(store, branch_id, own_only)
    rows = store.query(
        f"SELECT {group} AS label, COUNT(*) AS calls,"
        " SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,"
        f" SUM(cost) AS cost FROM llm_calls WHERE {clause} GROUP BY {group}",
        params,
    )
    return {
        (row["label"] or "-"): Usage(
            row["calls"], row["input_tokens"], row["output_tokens"], row["cost"]
        )
        for row in rows
    }


def agent_cost(store: Store, branch_id: str, agent: str) -> float:
    usage = by(store, branch_id, "agent").get(agent)
    return usage.cost if usage else 0.0
