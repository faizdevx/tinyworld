import pytest

from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.planner import Planner
from WORLD.AI.plans import Plan


def test_plan_stores_action_types():
    plan = Plan(
        goal_type=GoalType.SOCIALIZE,
        actions=[ActionType.SOCIALIZE],
    )

    assert plan.current_action() == ActionType.SOCIALIZE
    assert isinstance(plan.current_action(), ActionType)


def test_planner_uses_action_types():
    planner = Planner()

    goal = type(
        "GoalStub",
        (),
        {"goal_type": GoalType.EARN_MONEY},
    )()

    plan = planner.create_plan(
        npc=None,
        goal=goal,
        world=None,
    )

    assert plan.actions == [
        ActionType.GO_TO_WORK,
        ActionType.WORK,
    ]


def test_plan_rejects_raw_strings():
    with pytest.raises(TypeError, match="ActionType"):
        Plan(
            goal_type=GoalType.SOCIALIZE,
            actions=["socialize"],
        )
