from WORLD.NPCs.memory import Memory


def test_memory_supports_structured_episode():
    memory = Memory(
        day=2,
        hour=18,
        event="Ali gave Rahul food",
        importance=5,
        memory_type="event",
        location="General Store",
        participants=["Rahul", "Ali"],
    )

    assert memory.memory_type == "event"
    assert memory.timestamp == 42
    assert memory.location == "General Store"
    assert memory.participants == [
        "Rahul",
        "Ali",
    ]
    assert memory.event == "Ali gave Rahul food"


def test_timestamp_is_derived_from_day_and_hour():
    memory = Memory(
        day=3,
        hour=5,
        event="Worked at the farm",
        importance=1,
    )

    assert memory.timestamp == 53


def test_explicit_timestamp_is_preserved():
    memory = Memory(
        day=2,
        hour=18,
        event="Ali gave Rahul food",
        importance=5,
        timestamp=100,
    )

    assert memory.timestamp == 100


def test_structured_memory_defaults_are_independent():
    first = Memory(
        day=1,
        hour=8,
        event="Saw Ali",
        importance=1,
    )

    second = Memory(
        day=1,
        hour=9,
        event="Saw Sara",
        importance=1,
    )

    first.participants.append("Ali")

    assert first.participants == ["Ali"]
    assert second.participants == []


def test_memory_metadata_validation():
    try:
        Memory(
            day=1,
            hour=8,
            event="Saw Ali",
            importance=1,
            memory_type="",
        )
    except ValueError as exc:
        assert str(exc) == "Memory type cannot be empty."
    else:
        raise AssertionError(
            "Expected ValueError"
        )