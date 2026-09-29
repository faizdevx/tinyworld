import pytest

from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan


def test_plan_stores_goal_and_actions():
    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            ActionType.GO_TO_WORK,
            ActionType.WORK,
        ],
    )

    assert plan.goal_type == GoalType.EARN_MONEY
    assert plan.actions == [
        ActionType.GO_TO_WORK,
        ActionType.WORK,
    ]
    assert plan.current_step == 0


def test_plan_returns_current_action():
    plan = Plan(
        goal_type=GoalType.SURVIVE,
        actions=[
            ActionType.FIND_FOOD,
            ActionType.OBTAIN_FOOD,
            ActionType.EAT,
        ],
    )

    assert plan.current_action() == ActionType.FIND_FOOD

    plan.advance()

    assert plan.current_action() == ActionType.OBTAIN_FOOD


def test_plan_can_advance_through_all_actions():
    plan = Plan(
        goal_type=GoalType.SURVIVE,
        actions=[
            ActionType.FIND_FOOD,
            ActionType.OBTAIN_FOOD,
            ActionType.EAT,
        ],
    )

    plan.advance()
    plan.advance()
    plan.advance()

    assert plan.is_complete()
    assert plan.current_action() is None


def test_empty_plan_is_complete():
    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
    )

    assert plan.is_complete()
    assert plan.current_action() is None


def test_plan_rejects_raw_action_strings():
    with pytest.raises(TypeError, match="ActionType"):
        Plan(
            goal_type=GoalType.SOCIALIZE,
            actions=["socialize"],
        )
