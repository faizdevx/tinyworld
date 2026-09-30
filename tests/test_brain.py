from types import SimpleNamespace

from WORLD.AI.action import ActionType
from WORLD.AI.brain import Brain
from WORLD.AI.experience_reflection import (
    ExperienceReflector,
)
from WORLD.NPCs.memory import Memory


class FakePerception:
    def __init__(self):
        self.calls = []

    def observe(self, npc, world):
        self.calls.append((npc, world))
        return [
            SimpleNamespace(
                subject=npc.name,
                predicate="hunger",
                value=npc.hunger,
                confidence=1.0,
            )
        ]


class FakeGoalSystem:
    def evaluate_goals(self, npc, world):
        return []

    def get_long_term_goals(self, npc):
        return []

    def select_highest_priority(self, goals, current_day):
        return getattr(self, "selected_goal", None)

    def is_goal_complete(self, goal):
        return False


class FakeMemoryRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(
        self,
        npc,
        query,
        *,
        limit=5,
        min_importance=0.0,
        current_timestamp=None,
    ):
        self.calls.append(
            {
                "npc": npc,
                "query": query,
                "limit": limit,
                "min_importance": min_importance,
                "current_timestamp": current_timestamp,
            }
        )
        return []


class FakeDecisionSystem:
    def decide(self, npc, world):
        return SimpleNamespace(chosen_action="noop")


class FakeActionExecutor:
    def execute(self, npc, action, world):
        return True


class FakeReasoner:
    def __init__(self):
        self.calls = []

    def reason(
        self,
        npc,
        world,
        *,
        had_active_plan,
        current_goal,
        active_plan,
    ):
        self.calls.append(
            {
                "npc": npc,
                "world": world,
                "had_active_plan": had_active_plan,
                "current_goal": current_goal,
                "active_plan": active_plan,
            }
        )

        return SimpleNamespace(
            goal=current_goal,
            action=ActionType.EAT,
            rationale="test",
        )


class FakeReflection:
    def __init__(self):
        self.calls = []

    def reflect(
        self,
        npc,
        world,
        result,
        reasoning=None,
    ):
        self.calls.append(
            {
                "npc": npc,
                "world": world,
                "result": result,
                "reasoning": reasoning,
            }
        )

        return SimpleNamespace(
            action=(
                reasoning.action
                if reasoning is not None
                else None
            ),
            success=result,
            lesson="test",
        )


def test_brain_observes_npc_state():
    npc = SimpleNamespace(
        name="Rahul",
        hunger=75,
        active_plan=None,
        current_goal=None,
        long_term_goals=[],
        memories=[],
    )

    world = SimpleNamespace(
        clock=SimpleNamespace(day=1, hour=8)
    )
    perception = FakePerception()
    goal_system = FakeGoalSystem()
    goal_system.selected_goal = SimpleNamespace(
        goal_type=SimpleNamespace(value="test_goal")
    )
    memory_retriever = FakeMemoryRetriever()

    brain = Brain(
        npc=npc,
        perception=perception,
        goal_system=goal_system,
        planner=None,
        replanner=None,
        memory_retriever=memory_retriever,
        decision_system=FakeDecisionSystem(),
        action_executor=FakeActionExecutor(),
    )

    observations = brain.observe(world)

    assert observations[0].predicate == "hunger"
    assert observations[0].value == 75
    assert npc.beliefs == observations

    brain.think(world)

    assert memory_retriever.calls == [
        {
            "npc": npc,
            "query": "test_goal",
            "limit": 5,
            "min_importance": 0.0,
            "current_timestamp": 8,
        }
    ]


def test_brain_records_reasoning_result():
    npc = SimpleNamespace(
        name="Rahul",
        hunger=70,
        active_plan=None,
        current_goal=None,
        long_term_goals=[],
        memories=[],
    )

    world = SimpleNamespace(clock=SimpleNamespace(day=1))
    reasoner = FakeReasoner()

    brain = Brain(
        npc=npc,
        perception=FakePerception(),
        goal_system=FakeGoalSystem(),
        planner=None,
        replanner=None,
        memory_retriever=FakeMemoryRetriever(),
        decision_system=FakeDecisionSystem(),
        action_executor=FakeActionExecutor(),
        reasoner=reasoner,
    )

    brain.act(world, had_active_plan=False)

    assert brain.last_reasoning is not None
    assert brain.last_reasoning.action == ActionType.EAT
    assert brain.last_reasoning.rationale == "test"
    assert len(reasoner.calls) == 1


def test_brain_records_reflection_result():
    npc = SimpleNamespace(
        name="Rahul",
        hunger=70,
        active_plan=None,
        current_goal=None,
        long_term_goals=[],
        memories=[],
    )

    world = SimpleNamespace(clock=SimpleNamespace(day=1))
    reasoner = FakeReasoner()
    reflection = FakeReflection()

    brain = Brain(
        npc=npc,
        perception=FakePerception(),
        goal_system=FakeGoalSystem(),
        planner=None,
        replanner=None,
        memory_retriever=FakeMemoryRetriever(),
        decision_system=FakeDecisionSystem(),
        action_executor=FakeActionExecutor(),
        reasoner=reasoner,
        reflection=reflection,
    )

    result = brain.act(world, had_active_plan=False)
    brain.reflect(world, result)

    assert brain.last_reflection is not None
    assert brain.last_reflection.action == ActionType.EAT
    assert brain.last_reflection.success is True
    assert brain.last_reflection.lesson == "test"
    assert len(reflection.calls) == 1
    assert reflection.calls[0]["reasoning"] is brain.last_reasoning


def test_brain_lifecycle_calls_reflection_after_action():
    npc = SimpleNamespace(
        name="Rahul",
        hunger=70,
        active_plan=None,
        current_goal=None,
        long_term_goals=[],
        memories=[
            Memory(
                day=1,
                hour=10,
                event="Ali helped Rahul",
                importance=0.9,
            )
        ],
    )

    world = SimpleNamespace(clock=SimpleNamespace(day=1))
    reflection = FakeReflection()

    brain = Brain(
        npc=npc,
        perception=FakePerception(),
        goal_system=FakeGoalSystem(),
        planner=None,
        replanner=None,
        memory_retriever=FakeMemoryRetriever(),
        decision_system=FakeDecisionSystem(),
        action_executor=FakeActionExecutor(),
        reasoner=FakeReasoner(),
        reflection=reflection,
        experience_reflector=ExperienceReflector(),
    )

    brain.update(world)

    assert len(reflection.calls) == 1
    assert reflection.calls[0]["result"] is True
    assert reflection.calls[0]["reasoning"] is brain.last_reasoning
    assert brain.last_experience_reflection is None


def test_brain_can_reflect_on_memory():
    npc = SimpleNamespace(
        name="Rahul",
        memories=[],
        current_goal=None,
    )

    brain = Brain(
        npc=npc,
        perception=None,
        goal_system=None,
        planner=None,
        replanner=None,
        memory_retriever=None,
        decision_system=None,
        action_executor=None,
        experience_reflector=ExperienceReflector(),
    )

    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=0.9,
        participants=["Rahul", "Ali"],
    )

    reflection = brain.reflect_on_memory(
        memory,
    )

    assert reflection is not None
    assert brain.last_experience_reflection is reflection
    assert reflection.memory is memory


def test_brain_does_not_reflect_on_unimportant_memory():
    npc = SimpleNamespace(
        name="Rahul",
        memories=[],
        current_goal=None,
    )

    brain = Brain(
        npc=npc,
        perception=None,
        goal_system=None,
        planner=None,
        replanner=None,
        memory_retriever=None,
        decision_system=None,
        action_executor=None,
        experience_reflector=ExperienceReflector(),
    )

    memory = Memory(
        day=1,
        hour=10,
        event="Walked to the farm",
        importance=0.1,
    )

    reflection = brain.reflect_on_memory(
        memory,
    )

    assert reflection is None
    assert brain.last_experience_reflection is None
