from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def make_npc(
    name="Rahul",
    *,
    food=1,
    hunger=90,
    energy=100,
    location="Home",
):
    return NPC(
        name=name,
        role="worker",
        money=50,
        home="Home",
        location=location,
        food=food,
        hunger=hunger,
        energy=energy,
    )


def test_brain_runs_reasoning_and_reflection():
    world = World(seed=42)
    npc = make_npc()

    world.add_npc(npc)

    brain = npc.brain

    result = brain.update(world)

    assert result is True

    assert brain.last_reasoning is not None
    assert brain.last_reasoning.action == ActionType.EAT

    assert brain.last_reflection is not None
    assert brain.last_reflection.action == ActionType.EAT
    assert brain.last_reflection.success is True


def test_newly_created_plan_waits_until_next_cycle():
    world = World(seed=42)
    npc = make_npc()

    world.add_npc(npc)

    brain = npc.brain

    assert getattr(npc, "active_plan", None) is None

    brain.update(world)

    assert npc.active_plan is not None
    assert npc.active_plan.goal_type == GoalType.SATISFY_HUNGER

    # The plan was created during this cycle, so its first
    # planned step must not have been executed yet.
    assert npc.active_plan.current_step == 0


def test_existing_plan_executes_through_brain():
    world = World(seed=42)

    npc = make_npc(
        food=1,
        hunger=80,
    )

    world.add_npc(npc)

    npc.active_plan = Plan(
        goal_type=GoalType.SATISFY_HUNGER,
        actions=[
            ActionType.EAT,
        ],
    )

    result = npc.brain.update(world)

    assert result is True

    assert npc.food == 0
    assert npc.hunger == 40

    assert npc.active_plan.current_step == 1
    assert npc.active_plan.is_complete()

    assert npc.brain.last_reasoning is not None
    assert npc.brain.last_reasoning.action == ActionType.EAT

    assert npc.brain.last_reflection is not None
    assert npc.brain.last_reflection.success is True


def test_interrupted_plan_replans_through_brain():
    world = World(seed=42)

    npc = make_npc(
        food=1,
        hunger=20,
        energy=100,
        location="Village Farm",
    )

    world.add_npc(npc)

    long_term_goal = (
        world.agent_system.goal_system.create_long_term_goal(
            npc=npc,
            goal_type=GoalType.EARN_MONEY,
            priority=60,
            current_day=world.clock.day,
        )
    )

    npc.current_goal = long_term_goal

    npc.active_plan = world.agent_system.planner.create_plan(
        npc,
        long_term_goal,
        world,
    )

    assert npc.active_plan.goal_type == GoalType.EARN_MONEY
    assert not npc.active_plan.is_interrupted()

    # Unexpected condition appears before execution.
    npc.hunger = 95

    first_result = npc.brain.update(world)

    assert first_result is False
    assert npc.active_plan.is_interrupted()

    assert npc.brain.last_reasoning is not None
    assert npc.brain.last_reasoning.action == ActionType.GO_TO_WORK

    assert npc.brain.last_reflection is not None
    assert npc.brain.last_reflection.success is False

    # The next cognition cycle should detect the interrupted
    # plan and replace it with an urgent hunger plan.
    second_result = npc.brain.update(world)

    assert second_result is False

    assert npc.current_goal is not None
    assert (
        npc.current_goal.goal_type
        == GoalType.SATISFY_HUNGER
    )

    assert npc.active_plan is not None
    assert (
        npc.active_plan.goal_type
        == GoalType.SATISFY_HUNGER
    )

    assert not npc.active_plan.is_interrupted()
