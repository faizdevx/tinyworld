from WORLD.AI.action import ActionType
from WORLD.AI.action_executor import ActionExecutor
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def create_npc() -> NPC:
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )


def test_eat_action_changes_npc_state():
    world = World()
    rahul = create_npc()

    world.add_npc(rahul)

    rahul.food = 1
    rahul.hunger = 80
    rahul.energy = 50

    success = ActionExecutor().execute(
        rahul,
        ActionType.EAT,
        world,
    )

    assert success is True
    assert rahul.food == 0
    assert rahul.hunger == 40
    assert rahul.energy == 70


def test_sleep_action_restores_energy():
    world = World()
    rahul = create_npc()

    world.add_npc(rahul)

    rahul.energy = 40

    success = ActionExecutor().execute(
        rahul,
        ActionType.SLEEP,
        world,
    )

    assert success is True
    assert rahul.energy == 55



def test_shop_action_buys_food():
    world = World()
    rahul = create_npc()

    world.add_npc(rahul)

    rahul.money = 50
    rahul.food = 0

    success = ActionExecutor().execute(
        rahul,
        ActionType.SHOP,
        world,
    )

    assert success is True
    assert rahul.money == 45
    assert rahul.food == 1
    assert world.shop.food == 19
    assert world.shop.money == 105

def test_sleep_from_work_moves_npc_home():
    world = World()
    rahul = create_npc()

    world.add_npc(rahul)

    rahul.energy = 40
    rahul.location = "Village Farm"

    success = ActionExecutor().execute(
        rahul,
        ActionType.SLEEP,
        world,
    )

    assert success is True
    assert rahul.location == "House 1"
    assert rahul.energy == 55
