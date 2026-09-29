from types import SimpleNamespace

from WORLD.AI.brain import Brain


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
        return None

    def is_goal_complete(self, goal):
        return False


class FakeMemoryRetriever:
    def relevant_memories(self, npc, topic):
        return []


class FakeDecisionSystem:
    def decide(self, npc, world):
        return SimpleNamespace(chosen_action="noop")


class FakeActionExecutor:
    def execute(self, npc, action, world):
        return True


def test_brain_observes_npc_state():
    npc = SimpleNamespace(
        name="Rahul",
        hunger=75,
        active_plan=None,
        current_goal=None,
        long_term_goals=[],
        memories=[],
    )

    world = SimpleNamespace(clock=SimpleNamespace(day=1))
    perception = FakePerception()

    brain = Brain(
        npc=npc,
        perception=perception,
        goal_system=FakeGoalSystem(),
        planner=None,
        replanner=None,
        memory_retriever=FakeMemoryRetriever(),
        decision_system=FakeDecisionSystem(),
        action_executor=FakeActionExecutor(),
    )

    observations = brain.observe(world)

    assert observations[0].predicate == "hunger"
    assert observations[0].value == 75
    assert npc.beliefs == observations
