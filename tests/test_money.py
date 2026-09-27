from WORLD.NPCs.npc import NPC
from WORLD.Buildings.buildings import Building
from WORLD.Economy.money import transfer_money, total_money


def create_entities():
    rahul = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1"
    )

    shop = Building(
        name="General Store",
        building_type="shop",
        money=100
    )

    return rahul, shop


def test_money_transfer():
    rahul, shop = create_entities()

    result = transfer_money(rahul, shop, 5)

    assert result is True
    assert rahul.money == 45
    assert shop.money == 105


def test_money_cannot_be_created_or_destroyed():
    rahul, shop = create_entities()

    before = total_money([rahul, shop])

    transfer_money(rahul, shop, 5)

    after = total_money([rahul, shop])

    assert before == after


def test_transfer_fails_when_sender_cannot_afford():
    rahul, shop = create_entities()

    result = transfer_money(rahul, shop, 1000)

    assert result is False
    assert rahul.money == 50
    assert shop.money == 100


def test_multiple_transactions_preserve_total():
    rahul, shop = create_entities()

    before = total_money([rahul, shop])

    transfer_money(rahul, shop, 10)
    transfer_money(rahul, shop, 20)

    after = total_money([rahul, shop])

    assert before == after
    assert rahul.money == 20
    assert shop.money == 130