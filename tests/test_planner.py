from WORLD.AI.goal import Goal, GoalType
from WORLD.AI.planner import Planner
from WORLD.world import World


def create_goal(goal_type):
    return Goal(
        goal_type=goal_type,
        priority=50,
        created_day=1,
    )


def test_planner_creates_work_plan():
    world = World()
    planner = Planner()

    plan = planner.create_plan(
        None,
        create_goal(GoalType.EARN_MONEY),
        world,
    )

    assert plan.goal_type == GoalType.EARN_MONEY
    assert plan.actions == [
        "go_to_work",
        "work",
    ]


def test_planner_creates_survival_plan():
    world = World()
    planner = Planner()

    plan = planner.create_plan(
        None,
        create_goal(GoalType.SURVIVE),
        world,
    )

    assert plan.actions == [
        "find_food",
        "obtain_food",
        "eat",
    ]


def test_planner_creates_hunger_plan():
    world = World()
    planner = Planner()

    plan = planner.create_plan(
        None,
        create_goal(GoalType.SATISFY_HUNGER),
        world,
    )

    assert plan.actions == [
        "obtain_food",
        "eat",
    ]


def test_planner_creates_energy_plan():
    world = World()
    planner = Planner()

    plan = planner.create_plan(
        None,
        create_goal(GoalType.RESTORE_ENERGY),
        world,
    )

    assert plan.actions == [
        "go_home",
        "sleep",
    ]


def test_planner_creates_social_plan():
    world = World()
    planner = Planner()

    plan = planner.create_plan(
        None,
        create_goal(GoalType.SOCIALIZE),
        world,
    )

    assert plan.actions == [
        "socialize",
    ]


def test_unknown_goal_gets_empty_plan():
    world = World()
    planner = Planner()

    class UnknownGoalType:
        pass

    goal = Goal(
        goal_type=UnknownGoalType(),
        priority=10,
        created_day=1,
    )

    plan = planner.create_plan(
        None,
        goal,
        world,
    )

    assert plan.actions == []