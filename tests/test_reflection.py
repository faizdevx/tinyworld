from types import SimpleNamespace

from WORLD.AI.action import ActionType
from WORLD.AI.goal import Goal, GoalType
from WORLD.AI.reasoner import ReasoningResult
from WORLD.AI.reflection import Reflection


def make_reasoning():
    goal = Goal(
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        created_day=1,
    )

    return ReasoningResult(
        goal=goal,
        action=ActionType.WORK,
        rationale="follow_active_plan",
    )


def test_reflection_records_successful_action():
    result = Reflection().reflect(
        SimpleNamespace(),
        SimpleNamespace(),
        True,
        reasoning=make_reasoning(),
    )

    assert result.action == ActionType.WORK
    assert result.goal_type == GoalType.EARN_MONEY
    assert result.success is True
    assert result.lesson == "action_succeeded"


def test_reflection_records_failed_action():
    result = Reflection().reflect(
        SimpleNamespace(),
        SimpleNamespace(),
        False,
        reasoning=make_reasoning(),
    )

    assert result.action == ActionType.WORK
    assert result.goal_type == GoalType.EARN_MONEY
    assert result.success is False
    assert result.lesson == "action_failed"


def test_reflection_handles_no_action():
    result = Reflection().reflect(
        SimpleNamespace(),
        SimpleNamespace(),
        False,
        reasoning=None,
    )

    assert result.action is None
    assert result.goal_type is None
    assert result.success is False
    assert result.lesson == "no_action_attempted"
