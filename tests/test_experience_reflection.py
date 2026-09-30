from types import SimpleNamespace

from WORLD.AI.experience_reflection import (
    ExperienceReflector,
)
from WORLD.NPCs.memory import Memory


def make_npc():
    return SimpleNamespace(
        name="Rahul",
    )


def test_low_importance_memory_is_not_reflected():
    memory = Memory(
        day=1,
        hour=8,
        event="Walked to the farm",
        importance=0.2,
    )

    result = ExperienceReflector().reflect(
        make_npc(),
        memory,
    )

    assert result is None


def test_important_memory_produces_structured_reflection():
    memory = Memory(
        day=1,
        hour=10,
        event="Ali gave Rahul food",
        importance=0.9,
        location="General Store",
        participants=["Rahul", "Ali"],
    )

    result = ExperienceReflector().reflect(
        make_npc(),
        memory,
    )

    assert result is not None
    assert result.memory is memory
    assert result.observation == "Ali gave Rahul food"
    assert result.interpretation
    assert result.lesson
    assert result.suggested_behavior


def test_reflection_identifies_rejection_experience():
    memory = Memory(
        day=2,
        hour=12,
        event="Ali refused to lend Rahul money",
        importance=0.9,
        participants=["Rahul", "Ali"],
    )

    result = ExperienceReflector().reflect(
        make_npc(),
        memory,
    )

    assert result is not None
    assert (
        "expected outcome"
        in result.interpretation
    )
    assert (
        "alternative"
        in result.suggested_behavior
    )


def test_reflection_identifies_helpful_experience():
    memory = Memory(
        day=2,
        hour=12,
        event="Ali helped Rahul",
        importance=0.8,
        participants=["Rahul", "Ali"],
    )

    result = ExperienceReflector().reflect(
        make_npc(),
        memory,
    )

    assert result is not None
    assert "support" in result.interpretation
    assert "help" in result.suggested_behavior


def test_reflection_identifies_failed_experience():
    memory = Memory(
        day=3,
        hour=15,
        event="Failed to obtain food",
        importance=0.8,
        location="General Store",
    )

    result = ExperienceReflector().reflect(
        make_npc(),
        memory,
    )

    assert result is not None
    assert "did not produce" in result.interpretation
    assert "different approach" in result.suggested_behavior


def test_reflection_can_use_current_goal():
    memory = Memory(
        day=3,
        hour=15,
        event="Worked at the farm",
        importance=0.7,
    )

    result = ExperienceReflector().reflect(
        make_npc(),
        memory,
        current_goal="earn_money",
    )

    assert result is not None
    assert "earn_money" in result.interpretation
    assert "goal" in result.lesson