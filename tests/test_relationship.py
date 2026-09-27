from WORLD.NPCs.npc import NPC


def create_npc(name: str) -> NPC:
    return NPC(
        name=name,
        role="worker",
        money=50,
        home="House 1",
        location="House 1",
    )


def test_relationship_starts_at_zero():
    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    assert rahul.get_relationship(ali) == 0


def test_relationship_can_improve_and_worsen():
    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    rahul.change_relationship(ali, 10)

    assert rahul.get_relationship(ali) == 10

    rahul.change_relationship(ali, -5)

    assert rahul.get_relationship(ali) == 5


def test_relationship_cannot_exceed_maximum():
    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    rahul.change_relationship(ali, 150)

    assert rahul.get_relationship(ali) == 100


def test_relationship_cannot_go_below_minimum():
    rahul = create_npc("Rahul")
    ali = create_npc("Ali")

    rahul.change_relationship(ali, -150)

    assert rahul.get_relationship(ali) == -100