"""A short rolling plan per agent, stored as a memory so it forks with the branch."""

import json
from datetime import datetime

from tinyworld.agents.memory import MemoryStore, NewMemory

MAX_STEPS = 5
# An observation at least this important makes the agent reconsider its plan.
SURPRISE = 0.7


class Planner:
    def __init__(self, memory: MemoryStore) -> None:
        self.memory = memory

    def current(self, branch_id: str, agent: str) -> list[str]:
        latest = self.memory.latest(branch_id, agent, "plan")
        if latest is None:
            return []
        try:
            steps = json.loads(latest.text)
        except ValueError:
            return []
        return [step for step in steps if isinstance(step, str)]

    def store(
        self, branch_id: str, agent: str, steps: list[str], at_seq: int, now: datetime
    ) -> None:
        steps = [step.strip() for step in steps if step.strip()][:MAX_STEPS]
        if steps == self.current(branch_id, agent):
            return
        self.memory.write(
            branch_id,
            agent,
            [
                NewMemory(
                    kind="plan",
                    text=json.dumps(steps),
                    created_seq=at_seq,
                    sim_time=now,
                    importance=0.2,
                )
            ],
        )

    @staticmethod
    def should_reconsider(plan: list[str], new_importances: list[float]) -> bool:
        return not plan or any(value >= SURPRISE for value in new_importances)
