import re
from datetime import datetime
from pathlib import Path

import pytest

from tinyworld.core.entropy import Entropy, Fixed, ReplayMismatch
from tinyworld.core.store import Store


def branch():
    store = Store()
    world = store.create_world("w", datetime(2000, 1, 1, 8))
    return store, store.create_branch(world, "main")


def test_two_live_runs_differ():
    a, b = Entropy(), Entropy()
    assert [a.draw("x") for _ in range(8)] != [b.draw("x") for _ in range(8)]


def test_a_replay_reads_back_exactly_what_a_live_run_drew():
    store, br = branch()
    live = Entropy(store, br)
    made = [live.draw("a"), live.randint("b", 1, 6), live.choice("c", "xyz"), live.chance("d", 0.5)]
    order = live.order("e", [1, 2, 3, 4])
    again = Entropy.replaying(store, br)
    assert [again.draw("a"), again.randint("b", 1, 6), again.choice("c", "xyz"), again.chance("d", 0.5)] == made
    assert again.order("e", [1, 2, 3, 4]) == order
    assert again.remaining() == 0


def test_a_replay_that_asks_for_something_else_fails():
    store, br = branch()
    Entropy(store, br).draw("a")
    with pytest.raises(ReplayMismatch):
        Entropy.replaying(store, br).draw("b")
    with pytest.raises(ReplayMismatch):
        again = Entropy.replaying(store, br)
        again.draw("a")
        again.draw("a")


def test_helpers_stay_in_range():
    e = Entropy()
    assert all(1 <= e.randint("n", 1, 3) <= 3 for _ in range(200))
    assert {e.randint("n", 1, 3) for _ in range(200)} == {1, 2, 3}
    assert Fixed([0.99]).randint("n", 1, 3) == 3


def test_nothing_else_draws_unrecorded_randomness():
    """The single entropy source: the build fails if world code reaches for random itself."""
    root = Path(__file__).resolve().parent.parent / "tinyworld"
    allowed = {"core/entropy.py", "core/rng.py", "core/ids.py"}
    pattern = re.compile(r"^\s*(import random|from random import|import secrets|from secrets import)", re.M)
    offenders = [
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*.py")
        if str(path.relative_to(root)).replace("\\", "/") not in allowed
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
    uuid_use = [
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if str(p.relative_to(root)).replace("\\", "/").startswith("world/") and "uuid" in p.read_text(encoding="utf-8")
    ]
    assert uuid_use == []
