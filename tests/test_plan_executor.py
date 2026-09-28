from WORLD.AI.action import ActionType
from WORLD.AI.plan_executor import PlanExecutor
from WORLD.AI.plans import Plan
from WORLD.NPCs.npc import NPC
from WORLD.world import World


class FakeActionExecutor:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def execute(self, npc, action, world):
        self.calls.append(action)
        return self.result


def create_npc():
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="General Store",
    )


def test_plan_executor_runs_current_step():
    world = World()
    npc = create_npc()

    fake_executor = FakeActionExecutor()

    plan = Plan(
        goal_type=None,
        actions=["buy_food"],
    )

    executor = PlanExecutor(fake_executor)

    result = executor.execute_current_step(
        npc,
        plan,
        world,
    )

    assert result is True
    assert fake_executor.calls == [
        ActionType.SHOP,
    ]
    assert plan.current_step == 1


def test_plan_executor_does_not_advance_when_action_fails():
    world = World()
    npc = create_npc()

    fake_executor = FakeActionExecutor(
        result=False,
    )

    plan = Plan(
        goal_type=None,
        actions=["buy_food"],
    )

    executor = PlanExecutor(fake_executor)

    result = executor.execute_current_step(
        npc,
        plan,
        world,
    )

    assert result is False
    assert plan.current_step == 0


def test_completed_plan_does_not_execute():
    world = World()
    npc = create_npc()

    fake_executor = FakeActionExecutor()

    plan = Plan(
        goal_type=None,
        actions=["buy_food"],
        current_step=1,
    )

    executor = PlanExecutor(fake_executor)

    result = executor.execute_current_step(
        npc,
        plan,
        world,
    )

    assert result is False
    assert fake_executor.calls == []


def test_unknown_plan_step_does_not_advance():
    world = World()
    npc = create_npc()

    fake_executor = FakeActionExecutor()

    plan = Plan(
        goal_type=None,
        actions=["go_to_shop"],
    )

    executor = PlanExecutor(fake_executor)

    result = executor.execute_current_step(
        npc,
        plan,
        world,
    )

    assert result is False
    assert plan.current_step == 0
    assert fake_executor.calls == []