from WORLD.Map.position import Position


def test_position_creation():
    position = Position(2, 3)

    assert position.x == 2
    assert position.y == 3


def test_manhattan_distance():
    a = Position(2, 2)
    b = Position(5, 3)

    assert a.manhattan_distance_to(b) == 4


def test_position_move():
    position = Position(2, 2)

    new_position = position.move(3, -1)

    assert new_position == Position(5, 1)


def test_adjacent_position():
    a = Position(2, 2)
    b = Position(2, 3)

    assert a.is_adjacent_to(b) is True