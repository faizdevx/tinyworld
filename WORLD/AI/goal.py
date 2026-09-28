from dataclasses import dataclass
from enum import Enum


class GoalType(Enum):
    # Existing immediate goals
    SATISFY_HUNGER = "satisfy_hunger"
    RESTORE_ENERGY = "restore_energy"
    EARN_MONEY = "earn_money"
    SOCIALIZE = "socialize"

    # Phase 6 long-term goals
    SURVIVE = "survive"
    MAINTAIN_HOME = "maintain_home"
    BUILD_RELATIONSHIP = "build_relationship"
    HELP_FAMILY = "help_family"


@dataclass
class Goal:
    goal_type: GoalType
    priority: float
    created_day: int
    deadline_day: int | None = None
    progress: float = 0.0