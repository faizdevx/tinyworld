from WORLD.AI.action import ActionType
from WORLD.NPCs.npc import NPC
from WORLD.world import World
from types import SimpleNamespace
from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.goal_system import GoalSystem
from WORLD.AI.planner import Planner
from WORLD.AI.plans import Plan
from WORLD.AI.replanner import Replanner
from WORLD.system.agent import AgentSystem

class FakeDecision:
    def __init__(self, chosen_action):
        self.chosen_action = chosen_action


class FakeDecisionSystem:
    def __init__(self):
        self.calls = []

    def decide(self, npc, world):
        self.calls.append(npc)
        return FakeDecision(ActionType.EAT)


class FakeActionExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, npc, action, world):
        self.calls.append(
            (npc, action, world)
        )
        return True


class FakePerception:
    def observe(self, npc, world):
        return [
            SimpleNamespace(
                subject=npc.name,
                predicate="hunger",
                value=npc.hunger,
                confidence=1.0,
            )
        ]


def make_npc(
    *,
    name="Rahul",
    hunger=20,
    energy=80,
    money=50,
):
    return SimpleNamespace(
        name=name,
        hunger=hunger,
        energy=energy,
        money=money,
        food=1,
        location="Village",
        current_goal=None,
        active_plan=None,
        memories=[],
    )


def make_world(npc):
    return SimpleNamespace(
        npcs=[npc],
        clock=SimpleNamespace(day=1),
        action_executor=FakeActionExecutor(),
    )


def test_agent_updates_beliefs_from_perception():
    npc = make_npc(hunger=75)
    world = make_world(npc)

    decision_system = FakeDecisionSystem()

    agent = AgentSystem(
        decision_system=decision_system,
        perception=FakePerception(),
    )

    agent.update(world)

    assert npc.beliefs
    assert npc.beliefs[0].predicate == "hunger"
    assert npc.beliefs[0].value == 75


def test_agent_creates_goal_from_current_state():
    npc = make_npc(
        hunger=90,
        energy=80,
        money=50,
    )
    world = make_world(npc)

    agent = AgentSystem(
        decision_system=FakeDecisionSystem(),
        perception=FakePerception(),
    )

    agent.update(world)

    assert npc.current_goal is not None
    assert npc.current_goal.goal_type == GoalType.SATISFY_HUNGER


def test_agent_creates_plan_for_current_goal():
    npc = make_npc(
        hunger=90,
        energy=80,
        money=50,
    )
    world = make_world(npc)

    agent = AgentSystem(
        decision_system=FakeDecisionSystem(),
        perception=FakePerception(),
    )

    agent.update(world)

    assert npc.active_plan is not None
    assert npc.active_plan.goal_type == GoalType.SATISFY_HUNGER
    assert npc.active_plan.actions == [
        "obtain_food",
        "eat",
    ]


def test_agent_replans_interrupted_plan():
    npc = make_npc(
        hunger=95,
        energy=80,
        money=50,
    )

    npc.current_goal = SimpleNamespace(
        goal_type=GoalType.EARN_MONEY,
    )

    npc.active_plan = Plan(
        goal_type=GoalType.EARN_MONEY,
        actions=[
            "go_to_work",
            "work",
        ],
    )

    npc.active_plan.interrupt()

    world = make_world(npc)

    agent = AgentSystem(
        decision_system=FakeDecisionSystem(),
        perception=FakePerception(),
    )

    agent.update(world)

    assert npc.active_plan is not None
    assert npc.active_plan.goal_type == GoalType.SATISFY_HUNGER
    assert not npc.active_plan.is_interrupted()


def test_agent_still_uses_decision_system_for_action():
    npc = make_npc()

    world = make_world(npc)

    decision_system = FakeDecisionSystem()

    agent = AgentSystem(
        decision_system=decision_system,
        perception=FakePerception(),
    )

    agent.update(world)

    assert len(decision_system.calls) == 1

    assert len(world.action_executor.calls) == 1

    called_npc, action, called_world = (
        world.action_executor.calls[0]
    )

    assert called_npc is npc
    assert action == ActionType.EAT
    assert called_world is world

def test_agent_system_makes_one_decision_and_executes_it():
    world = World()

    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
        hunger=85,
        energy=50,
        food=1,
    )

    world.add_npc(rahul)

    world.agent_system.update(world)

    # Rahul has food and high hunger,
    # so the decision should be EAT.
    assert rahul.food == 0
    assert rahul.hunger == 45
    assert rahul.energy == 70