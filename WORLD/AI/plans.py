from dataclasses import dataclass, field

from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType


@dataclass
class Plan:
    goal_type: GoalType
    actions: list[ActionType] = field(default_factory=list)
    current_step: int = 0
    interrupted: bool = False

    def __post_init__(self) -> None:
        if not all(
            isinstance(action, ActionType)
            for action in self.actions
        ):
            raise TypeError(
                "Plan actions must be ActionType values"
            )

    def current_action(self) -> ActionType | None:
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
