"""Spending caps and the order in which the simulation degrades under them."""

from dataclasses import dataclass
from typing import Literal

from tinyworld.core.store import Store
from tinyworld.llm import ledger

Level = Literal["ok", "lengthen", "demote", "pause"]

LENGTHEN_AT = 0.70
DEMOTE_AT = 0.85


@dataclass
class Budget:
    """A cost cap for one branch.

    As spending approaches the cap the simulation first takes longer steps,
    then runs everyone on the cheap tier, then stops and asks.
    """

    store: Store
    branch_id: str
    run_cap: float | None = None
    agent_cap: float | None = None

    def spent(self) -> float:
        return ledger.total(self.store, self.branch_id).cost

    def remaining(self) -> float | None:
        return None if self.run_cap is None else max(0.0, self.run_cap - self.spent())

    def fraction(self) -> float:
        if not self.run_cap:
            return 0.0
        return self.spent() / self.run_cap

    def level(self) -> Level:
        fraction = self.fraction()
        if self.run_cap is not None and fraction >= 1.0:
            return "pause"
        if fraction >= DEMOTE_AT:
            return "demote"
        if fraction >= LENGTHEN_AT:
            return "lengthen"
        return "ok"

    def agent_over_cap(self, agent_id: str) -> bool:
        if self.agent_cap is None:
            return False
        return ledger.agent_cost(self.store, self.branch_id, agent_id) >= self.agent_cap

    def raise_cap(self, amount: float) -> None:
        self.run_cap = (self.run_cap or 0.0) + amount
