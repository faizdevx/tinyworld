from types import SimpleNamespace

from WORLD.AI.action import ActionType
from WORLD.AI.goal import Goal, GoalType
from WORLD.AI.plans import Plan
from WORLD.AI.reasoner import Reasoner


class FakeDecisionSystem:
    def __init__(self, action):
        self.action = action
        self.calls = []

    def decide(self, npc, world):
        self.calls.append((npc, world))
        return SimpleNamespace(chosen_action=self.action)


def make_goal():
    return Goal(
        goal_type=GoalType.SATISFY_HUNGER,
        priority=80,
        created_day=1,
    )


def test_reasoner_follows_existing_plan():
    decision_system = FakeDecisionSystem(ActionType.SLEEP)
    reasoner = Reasoner(decision_system=decision_system)
    plan = Plan(
        goal_type=GoalType.SATISFY_HUNGER,
        actions=[ActionType.EAT],
    )

    result = reasoner.reason(
        SimpleNamespace(),
        SimpleNamespace(),
        had_active_plan=True,
        current_goal=make_goal(),
        active_plan=plan,
    )

    assert result.action == ActionType.EAT
    assert result.rationale == "follow_active_plan"
    assert result.goal.goal_type == GoalType.SATISFY_HUNGER
    assert decision_system.calls == []


def test_reasoner_uses_decision_fallback_without_existing_plan():
    decision_system = FakeDecisionSystem(ActionType.SOCIALIZE)
    reasoner = Reasoner(decision_system=decision_system)

    result = reasoner.reason(
        SimpleNamespace(),
        SimpleNamespace(),
        had_active_plan=False,
        current_goal=make_goal(),
        active_plan=None,
    )

    assert result.action == ActionType.SOCIALIZE
    assert result.rationale == "legacy_decision_fallback"
    assert len(decision_system.calls) == 1


def test_reasoner_does_not_execute_actions():
    reasoner = Reasoner(
        decision_system=FakeDecisionSystem(ActionType.EAT)
    )

    result = reasoner.reason(
        SimpleNamespace(),
        SimpleNamespace(),
        had_active_plan=False,
        current_goal=None,
        active_plan=None,
    )

    assert result.action == ActionType.EAT
    assert not hasattr(result, "executed")
