from WORLD.AI.goal import GoalType
from WORLD.AI.plan_executor import PlanExecutor
from WORLD.AI.plans import Plan
from WORLD.NPCs.npc import NPC
from WORLD.world import World


class FakeActionExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, npc, action, world):
        self.calls.append(action)
        return True


def create_npc():
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="Village Farm",
        hunger=20,
        energy=80,
    )


def test_plan_is_not_interrupted_under_normal_conditions():
    world = World()
    npc = create_npc()

    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            "work",
        ],
    )

    executor = PlanExecutor(
        FakeActionExecutor()
    )

    assert executor.should_interrupt(
        npc,
        plan,
    ) is False


def test_high_hunger_interrupts_money_plan():
    world = World()
    npc = create_npc()
    npc.hunger = 95

    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            "work",
        ],
    )

    executor = PlanExecutor(
        FakeActionExecutor()
    )

    assert executor.should_interrupt(
        npc,
        plan,
    ) is True


def test_hunger_goal_is_not_interrupted_by_hunger():
    world = World()
    npc = create_npc()
    npc.hunger = 95

    plan = Plan(
        goal_type=GoalType.SATISFY_HUNGER,
        actions=[
            "obtain_food",
            "eat",
        ],
    )

    executor = PlanExecutor(
        FakeActionExecutor()
    )

    assert executor.should_interrupt(
        npc,
        plan,
    ) is False


def test_interrupt_marks_plan():
    world = World()
    npc = create_npc()
    npc.hunger = 95

    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            "work",
        ],
    )

    executor = PlanExecutor(
        FakeActionExecutor()
    )

    assert executor.interrupt_if_needed(
        npc,
        plan,
    ) is True

    assert plan.is_interrupted() is True
    assert plan.current_action() is None


def test_interrupted_plan_does_not_execute():
    world = World()
    npc = create_npc()
    npc.hunger = 95

    action_executor = FakeActionExecutor()

    plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            "work",
        ],
    )

    executor = PlanExecutor(action_executor)

    result = executor.execute_current_step(
        npc,
        plan,
        world,
    )

    assert result is False
    assert action_executor.calls == []
    assert plan.is_interrupted() is True