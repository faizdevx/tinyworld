"""What a run will cost, before it runs, and a budget that slows the town down instead of overspending.

``estimate`` runs a short probe on a fork of the world (the same engine, the same
model route, a few simulated hours), counts model calls and tokens by role per
resident-hour, then scales to the people and days asked for and prices them with
the configured model prices. It also reports the calls and dollars per resident
per simulated day, and which role is the dear one.

``DailyBudget`` caps spending per simulated day as well as per run. Over 70% of a
cap, residents' pauses lengthen; over 85%, everyone falls back to the cheap
tier and pauses lengthen again; at the cap the town stops and asks.
"""

from dataclasses import dataclass, field

from tinyworld.llm import ledger
from tinyworld.sim.budget import Budget, Level


@dataclass
class Estimate:
    residents: int
    days: float
    calls: int
    input_tokens: int
    output_tokens: int
    dollars: float
    by_role: dict[str, dict] = field(default_factory=dict)
    per_resident_day_calls: float = 0.0
    per_resident_day_dollars: float = 0.0
    probe_hours: float = 0.0
    growth: float = 1.0

    def as_dict(self) -> dict:
        return self.__dict__ | {}

    def say(self) -> str:
        return (
            f"{self.residents} residents for {self.days:g} days: about {self.calls:,} calls "
            f"({self.input_tokens / 1e6:.1f}M tokens in, {self.output_tokens / 1e6:.2f}M out), "
            f"${self.dollars:,.2f}; {self.per_resident_day_calls:.1f} calls and "
            f"${self.per_resident_day_dollars:.3f} per resident per day."
        )


def measure(store, branch_id: str, config, *, own_only: bool = True) -> dict[str, dict]:
    """Calls, tokens and dollars by role for a branch."""
    out = {}
    for role, usage in ledger.by(store, branch_id, "role", own_only=own_only).items():
        out[role] = {
            "calls": usage.calls, "input": usage.input_tokens or 0, "output": usage.output_tokens or 0,
            "cost": usage.cost or 0.0,
        }
    return out


def scale(by_role: dict[str, dict], factor: float, growth: float = 1.0) -> dict[str, dict]:
    return {
        role: {
            "calls": round(v["calls"] * factor), "input": round(v["input"] * factor * growth),
            "output": round(v["output"] * factor), "cost": v["cost"] * factor * (1 + (growth - 1) * 0.7),
        }
        for role, v in by_role.items()
    }


async def estimate(
    base_session, advance, residents_target: int, days: float, config, *, probe_hours: float = 24.0,
) -> Estimate:
    """Probe a fork for ``probe_hours`` (via ``advance(branch, hours)``), then extrapolate.

    ``advance`` is an async function that runs a branch for that many simulated hours with the
    engine and model the real run will use.
    """
    seq = base_session.state.seq
    probe = base_session.fork(seq, "cost-probe")
    residents_probe = max(1, len([p for p in probe.state.people() if p.attrs.get("persona")]))
    half = probe_hours / 2
    await advance(probe, half)
    first = measure(probe.store, probe.branch_id, config)
    await advance(probe, half)
    both = measure(probe.store, probe.branch_id, config)
    second = {
        role: {k: both[role][k] - first.get(role, {}).get(k, 0) for k in both[role]} for role in both
    }
    # People's days have a shape (work by day, choices in the evening), so the probe should cover a
    # whole day. Prompts get longer as memory builds, but the compactor bounds it: growth is the
    # change in tokens per call between the two halves, kept within limits.
    calls1 = sum(v["calls"] for v in first.values()) or 1
    calls2 = sum(v["calls"] for v in second.values()) or 1
    per_call_1 = (sum(v["input"] for v in first.values()) or 1) / calls1
    per_call_2 = sum(v["input"] for v in second.values()) / calls2
    growth = max(1.0, min(1.5, 1 + (per_call_2 / per_call_1 - 1) * 0.5))
    factor = (residents_target / residents_probe) * (days * 24 / probe_hours)
    scaled = scale(both, factor, growth)
    calls = sum(v["calls"] for v in scaled.values())
    dollars = sum(v["cost"] for v in scaled.values())
    return Estimate(
        residents=residents_target, days=days, calls=calls,
        input_tokens=sum(v["input"] for v in scaled.values()), output_tokens=sum(v["output"] for v in scaled.values()),
        dollars=round(dollars, 4), by_role=scaled,
        per_resident_day_calls=calls / max(1, residents_target) / max(days, 1e-9),
        per_resident_day_dollars=dollars / max(1, residents_target) / max(days, 1e-9),
        probe_hours=probe_hours, growth=round(growth, 3),
    )


@dataclass
class DailyBudget(Budget):
    """A budget with a cap per simulated day as well as per run."""

    day_cap: float | None = None
    _day: object = None
    _day_start: float = 0.0

    def tick_day(self, sim_time) -> None:
        day = sim_time.date()
        if self._day != day:
            self._day, self._day_start = day, self.spent()

    def day_spent(self) -> float:
        return max(0.0, self.spent() - self._day_start)

    def level(self) -> Level:
        base = super().level()
        if not self.day_cap:
            return base
        f = self.day_spent() / self.day_cap
        day = "pause" if f >= 1.0 else "demote" if f >= 0.85 else "lengthen" if f >= 0.70 else "ok"
        order = ["ok", "lengthen", "demote", "pause"]
        return max(base, day, key=order.index)
