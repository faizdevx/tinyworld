
from WORLD.world import World
from WORLD.NPCs.npc import NPC
from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan



def test_long_term_goal_survives_multiple_simulation_days():
    world = World(seed=42)

    npc = NPC(
        name="Rahul",
        role="worker",
        money=10,
        home="Home",
        location="Home",
    )

    world.add_npc(npc)

    goal = world.agent_system.goal_system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=world.clock.day,
    )

    initial_day = world.clock.day

    world.clock.hour = 0

    from WORLD.Simulation.simulation import Simulation

    simulation = Simulation(world)
    simulation.run(48)

    assert world.clock.day > initial_day
    assert goal in npc.long_term_goals
    assert goal.progress == 0.0


def make_npc():
    return NPC(
        name="Rahul",
        role="worker",
        money=100,
        home="Home",
        location="Home",
        hunger=0,
        energy=100,
    )


def test_long_term_goal_becomes_current_goal():
    world = World(seed=42)
    npc = make_npc()
    world.add_npc(npc)

    goal = world.agent_system.goal_system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=world.clock.day,
    )

    world.agent_system._update_goals(npc, world)

    assert npc.current_goal is goal
    assert npc.current_goal.goal_type == GoalType.EARN_MONEY


def test_urgent_need_overrides_lower_priority_long_term_goal():
    world = World(seed=42)
    npc = make_npc()
    npc.hunger = 90
    world.add_npc(npc)

    long_term_goal = (
        world.agent_system.goal_system.create_long_term_goal(
            npc=npc,
            goal_type=GoalType.EARN_MONEY,
            priority=60,
            current_day=world.clock.day,
        )
    )

    world.agent_system._update_goals(npc, world)

    assert npc.current_goal is not long_term_goal
    assert (
        npc.current_goal.goal_type
        == GoalType.SATISFY_HUNGER
    )


def test_completed_long_term_goal_is_not_selected():
    world = World(seed=42)
    npc = make_npc()
    world.add_npc(npc)

    goal = world.agent_system.goal_system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=world.clock.day,
        progress=1.0,
    )

    world.agent_system._update_goals(npc, world)

    assert npc.current_goal is None
    assert goal in npc.long_term_goals


def test_active_plan_executes_supported_action():
    world = World(seed=42)

    npc = NPC(
        name="Sara",
        role="worker",
        money=50,
        home="Home",
        location="Home",
        food=1,
        hunger=80,
        energy=100,
    )

    world.add_npc(npc)

    npc.active_plan = Plan(
        goal_type=GoalType.SATISFY_HUNGER,
        actions=["eat"],
    )

    world.agent_system._execute_plan_or_decide(
        npc,
        world,
    )

    assert npc.hunger == 40
    assert npc.food == 0
    assert npc.active_plan.current_step == 1

def test_multi_step_plan_persists_across_agent_updates():
    world = World(seed=42)

    npc = NPC(
        name="Rahul",
        role="worker",
        money=50,
        home="Home",
        location="Home",
        food=2,
        hunger=80,
        energy=100,
    )

    world.add_npc(npc)

    npc.active_plan = Plan(
        goal_type=GoalType.SATISFY_HUNGER,
        actions=["eat", "eat"],
    )

    world.agent_system.update(world)

    assert npc.active_plan.current_step == 1
    assert npc.food == 1

    world.agent_system.update(world)

    assert npc.active_plan.current_step == 2
    assert npc.food == 0
    assert npc.active_plan.is_complete()
    
def test_plan_is_interrupted_and_replanned_when_hunger_becomes_critical():
    world = World(seed=42)

    npc = NPC(
        name="Rahul",
        role="worker",
        money=50,
        home="Home",
        location="Farm",
        food=1,
        hunger=20,
        energy=100,
    )

    world.add_npc(npc)

    work_goal = world.agent_system.goal_system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=world.clock.day,
    )

    npc.current_goal = work_goal

    npc.active_plan = world.agent_system.planner.create_plan(
        npc,
        work_goal,
        world,
    )

    assert npc.active_plan.goal_type == GoalType.EARN_MONEY
    assert not npc.active_plan.is_interrupted()

    # Unexpected condition.
    npc.hunger = 95

    # Interruption is handled by PlanExecutor.
    result = world.agent_system._execute_plan_or_decide(
        npc,
        world,
    )

    assert result is False
    assert npc.active_plan.is_interrupted()

    # Replanning happens as a separate cognition phase.
    world.agent_system._update_goals(
        npc,
        world,
    )

    world.agent_system._update_plan(
        npc,
        world,
    )

    assert npc.current_goal.goal_type == GoalType.SATISFY_HUNGER
    assert npc.active_plan.goal_type == GoalType.SATISFY_HUNGER
    assert not npc.active_plan.is_interrupted()
    assert npc.active_plan.current_step == 0