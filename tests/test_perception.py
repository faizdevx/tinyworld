from types import SimpleNamespace

from WORLD.AI.perception import Perception


def make_npc(
    name="Rahul",
    hunger=40,
    energy=75,
    money=100,
    location="Village",
):
    return SimpleNamespace(
        name=name,
        hunger=hunger,
        energy=energy,
        money=money,
        location=location,
    )


def make_world(npc):
    return SimpleNamespace(
        npcs=[npc],
    )


def beliefs_by_predicate(beliefs):
    return {
        belief.predicate: belief
        for belief in beliefs
    }


def test_perception_observes_hunger():
    npc = make_npc(hunger=65)
    world = make_world(npc)

    beliefs = Perception().observe(npc, world)
    belief_map = beliefs_by_predicate(beliefs)

    assert belief_map["hunger"].value == 65


def test_perception_observes_energy():
    npc = make_npc(energy=25)
    world = make_world(npc)

    beliefs = Perception().observe(npc, world)
    belief_map = beliefs_by_predicate(beliefs)

    assert belief_map["energy"].value == 25


def test_perception_observes_money():
    npc = make_npc(money=45)
    world = make_world(npc)

    beliefs = Perception().observe(npc, world)
    belief_map = beliefs_by_predicate(beliefs)

    assert belief_map["money"].value == 45


def test_perception_observes_location():
    npc = make_npc(location="Village Farm")
    world = make_world(npc)

    beliefs = Perception().observe(npc, world)
    belief_map = beliefs_by_predicate(beliefs)

    assert belief_map["location"].value == "Village Farm"


def test_perception_uses_perfect_confidence():
    npc = make_npc()
    world = make_world(npc)

    beliefs = Perception().observe(npc, world)

    assert all(
        belief.confidence == 1.0
        for belief in beliefs
    )


def test_perception_returns_current_state():
    npc = make_npc(
        hunger=80,
        energy=20,
        money=10,
        location="Village Shop",
    )
    world = make_world(npc)

    beliefs = Perception().observe(npc, world)
    belief_map = beliefs_by_predicate(beliefs)

    assert belief_map["hunger"].value == 80
    assert belief_map["energy"].value == 20
    assert belief_map["money"].value == 10
    assert belief_map["location"].value == "Village Shop"