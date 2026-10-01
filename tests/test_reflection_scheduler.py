from types import SimpleNamespace

from WORLD.AI.brain import Brain
from WORLD.AI.experience_reflection import ExperienceReflector
from WORLD.AI.reflection_scheduler import ReflectionScheduler
from WORLD.NPCs.memory import Memory


def make_memory(importance: float) -> Memory:
    return Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=importance,
        participants=["Rahul", "Ali"],
    )


def test_routine_experience_does_not_trigger_reflection():
    decision = ReflectionScheduler().should_reflect(make_memory(0.2))

    assert decision.should_reflect is False
    assert decision.reason == "routine_experience"


def test_important_experience_triggers_reflection():
    decision = ReflectionScheduler().should_reflect(make_memory(0.6))

    assert decision.should_reflect is True
    assert decision.reason == "important_experience"


def test_critical_experience_triggers_immediate_reflection():
    decision = ReflectionScheduler().should_reflect(make_memory(0.9))

    assert decision.should_reflect is True
    assert decision.reason == "critical_experience"


def test_brain_scheduled_reflection_ignores_routine_memory():
    npc = SimpleNamespace(name="Rahul")
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
        reflection_scheduler=ReflectionScheduler(),
    )
    memory = Memory(
        day=1,
        hour=10,
        event="Walked to farm",
        importance=0.1,
    )

    result = brain.scheduled_reflect(memory)

    assert result is None


def test_brain_scheduled_reflection_processes_important_memory():
    npc = SimpleNamespace(name="Rahul")
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
        reflection_scheduler=ReflectionScheduler(),
    )
    memory = Memory(
        day=1,
        hour=10,
        event="Ali helped Rahul",
        importance=0.8,
        participants=["Rahul", "Ali"],
    )

    result = brain.scheduled_reflect(memory)

    assert result is not None
    assert result.memory is memory


def test_brain_reports_when_a_memory_should_be_reflected():
    npc = SimpleNamespace(name="Rahul")
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
        reflection_scheduler=ReflectionScheduler(),
    )

    assert brain.should_reflect_on_memory(make_memory(0.8)) is True
    assert brain.should_reflect_on_memory(make_memory(0.2)) is False
