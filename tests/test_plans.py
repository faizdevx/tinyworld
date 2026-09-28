from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan


def test_plan_stores_goal_and_actions():
    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            "go_to_work",
            "work",
        ],
    )

    assert plan.goal_type == GoalType.EARN_MONEY
    assert plan.actions == [
        "go_to_work",
        "work",
    ]
    assert plan.current_step == 0


def test_plan_returns_current_action():
    plan = Plan(
        goal_type=GoalType.SURVIVE,
        actions=[
            "find_food",
            "obtain_food",
            "eat",
        ],
    )

    assert plan.current_action() == "find_food"

    plan.advance()

    assert plan.current_action() == "obtain_food"


def test_plan_can_advance_through_all_actions():
    plan = Plan(
        goal_type=GoalType.SURVIVE,
        actions=[
            "find_food",
            "obtain_food",
            "eat",
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