from dataclasses import dataclass, field
from WORLD.AI.goal import GoalType


@dataclass
class Plan:
    goal_type: GoalType
    actions: list[str] = field(default_factory=list)
    current_step: int = 0
    interrupted: bool = False

    def current_action(self) -> str | None:
        if self.is_complete() or self.interrupted:
            return None

        return self.actions[self.current_step]

    def is_complete(self) -> bool:
        return self.current_step >= len(self.actions)

    def advance(self) -> None:
        if not self.is_complete() and not self.interrupted:
            self.current_step += 1

    def interrupt(self) -> None:
        self.interrupted = True

    def is_interrupted(self) -> bool:
        return self.interrupted