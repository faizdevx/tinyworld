import pytest

from WORLD.NPCs.npc import NPC
from WORLD.Social.reputation import ReputationSystem


def create_npc(
    name="Rahul",
    reputation=0,
):
    return NPC(
        name=name,
        role="worker",
        money=50,
        home="House 1",
        location="House 1",
        reputation=reputation,
    )


def test_npc_starts_with_zero_reputation():
    npc = create_npc()

    assert npc.reputation == 0


def test_reputation_can_increase():
    npc = create_npc()

    ReputationSystem().increase(
        npc,
        10,
    )

    assert npc.reputation == 10


def test_reputation_can_decrease():
    npc = create_npc(
        reputation=10,
    )

    ReputationSystem().decrease(
        npc,
        5,
    )

    assert npc.reputation == 5


def test_reputation_cannot_exceed_maximum():
    npc = create_npc(
        reputation=90,
    )

    ReputationSystem().increase(
        npc,
        50,
    )

    assert npc.reputation == 100


def test_reputation_cannot_go_below_minimum():
    npc = create_npc(
        reputation=-90,
    )

    ReputationSystem().decrease(
        npc,
        50,
    )

    assert npc.reputation == -100


def test_negative_increase_is_rejected():
    npc = create_npc()

    with pytest.raises(ValueError):
        ReputationSystem().increase(
            npc,
            -1,
        )


def test_negative_decrease_is_rejected():
    npc = create_npc()

    with pytest.raises(ValueError):
        ReputationSystem().decrease(
            npc,
            -1,
        )


def test_cooperation_increases_reputation():
    npc = create_npc()

    ReputationSystem().apply_cooperation(npc)

    assert npc.reputation == 5


def test_conflict_decreases_reputation():
    npc = create_npc()

    ReputationSystem().apply_conflict(npc)

    assert npc.reputation == -5


def test_reputation_can_start_near_upper_bound():
    npc = create_npc(
        reputation=99,
    )

    ReputationSystem().apply_cooperation(npc)

    assert npc.reputation == 100


def test_reputation_can_start_near_lower_bound():
    npc = create_npc(
        reputation=-99,
    )

    ReputationSystem().apply_conflict(npc)

    assert npc.reputation == -100