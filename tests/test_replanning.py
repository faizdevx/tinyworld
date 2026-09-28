from types import SimpleNamespace

from WORLD.AI.goal import GoalType
from WORLD.AI.goal_system import GoalSystem
from WORLD.AI.planner import Planner
from WORLD.AI.plans import Plan
from WORLD.AI.replanner import Replanner


def make_npc(
    *,
    name="TestNPC",
    hunger=20,
    energy=80,
    money=50,
    location="Village",
):
    return SimpleNamespace(
        name=name,
        hunger=hunger,
        energy=energy,
        money=money,
        location=location,
        current_goal=None,
        active_plan=None,
    )


def make_world(npc, day=1):
    return SimpleNamespace(
        npcs=[npc],
        clock=SimpleNamespace(day=day),
    )


def make_replanner():
    return Replanner(
        goal_system=GoalSystem(),
        planner=Planner(),
    )


def test_active_plan_does_not_require_replanning():
    npc = make_npc()

    npc.active_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=["go_to_work", "work"],
    )

    replanner = make_replanner()

    assert replanner.needs_replanning(npc) is False


def test_interrupted_plan_requires_replanning():
    npc = make_npc()

    npc.active_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=["go_to_work", "work"],
    )

    npc.active_plan.interrupt()

    replanner = make_replanner()

    assert replanner.needs_replanning(npc) is True


def test_replanning_selects_current_highest_priority_goal():
    npc = make_npc(
        hunger=95,
        money=0,
    )

    npc.active_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=["go_to_work", "work"],
    )

    npc.active_plan.interrupt()

    world = make_world(npc)

    replanner = make_replanner()

    new_plan = replanner.replan(npc, world)

    assert new_plan is not None
    assert npc.current_goal is not None
    assert npc.current_goal.goal_type == GoalType.SATISFY_HUNGER


def test_replanning_replaces_interrupted_plan():
    npc = make_npc(hunger=95)

    old_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=["go_to_work", "work"],
    )

    old_plan.interrupt()
    npc.active_plan = old_plan

    world = make_world(npc)

    replanner = make_replanner()

    new_plan = replanner.replan(npc, world)

    assert new_plan is not old_plan
    assert npc.active_plan is new_plan
    assert not new_plan.is_interrupted()


def test_replanning_creates_plan_for_selected_goal():
    npc = make_npc(hunger=95)

    old_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=["go_to_work", "work"],
    )

    old_plan.interrupt()
    npc.active_plan = old_plan

    world = make_world(npc)

    replanner = make_replanner()

    new_plan = replanner.replan(npc, world)

    assert new_plan.goal_type == GoalType.SATISFY_HUNGER
    assert new_plan.actions == ["obtain_food", "eat"]


def test_no_replanning_occurs_without_interruption():
    npc = make_npc(hunger=95)

    npc.active_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=["go_to_work", "work"],
    )

    world = make_world(npc)

    replanner = make_replanner()

    result = replanner.replan(npc, world)

    assert result is None
    assert npc.active_plan.actions == ["go_to_work", "work"]