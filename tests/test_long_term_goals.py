from types import SimpleNamespace

from WORLD.AI.goal import GoalType
from WORLD.AI.goal_system import GoalSystem


def make_npc():
    return SimpleNamespace(
        name="Rahul",
    )


def test_npc_can_have_a_long_term_goal():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
    )

    goals = system.get_long_term_goals(npc)

    assert len(goals) == 1
    assert goals[0] is goal
    assert goals[0].goal_type == GoalType.EARN_MONEY


def test_long_term_goal_persists_on_npc():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
    )

    goals_day_one = system.get_long_term_goals(npc)

    # Simulate later ticks.
    goals_day_two = system.get_long_term_goals(npc)
    goals_day_ten = system.get_long_term_goals(npc)

    assert goals_day_one[0] is goal
    assert goals_day_two[0] is goal
    assert goals_day_ten[0] is goal


def test_long_term_goal_stores_creation_day():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.MAINTAIN_HOME,
        priority=50,
        current_day=4,
    )

    assert goal.created_day == 4


def test_long_term_goal_progress_can_increase():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
        progress=0.45,
    )

    system.update_goal_progress(
        goal,
        0.70,
    )

    assert goal.progress == 0.70


def test_long_term_goal_is_complete_at_full_progress():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
        progress=1.0,
    )

    assert system.is_goal_complete(goal) is True


def test_incomplete_goal_is_not_complete():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
        progress=0.99,
    )

    assert system.is_goal_complete(goal) is False


def test_completed_goal_can_be_removed():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
        progress=1.0,
    )

    removed = system.remove_completed_goal(
        npc,
        goal,
    )

    assert removed is True
    assert system.get_long_term_goals(npc) == []


def test_incomplete_goal_cannot_be_removed():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
        progress=0.50,
    )

    removed = system.remove_completed_goal(
        npc,
        goal,
    )

    assert removed is False
    assert system.get_long_term_goals(npc) == [goal]


def test_duplicate_goal_is_not_added_twice():
    npc = make_npc()
    system = GoalSystem()

    goal = system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=1,
    )

    system.add_long_term_goal(npc, goal)

    assert system.get_long_term_goals(npc) == [goal]