from WORLD.AI.goal import GoalType
from WORLD.AI.goal_system import GoalSystem
from WORLD.NPCs.npc import NPC


def create_npc() -> NPC:
    return NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )


def test_high_hunger_creates_hunger_goal():
    npc = create_npc()
    npc.hunger = 80

    goals = GoalSystem().get_goals(npc)

    assert GoalType.SATISFY_HUNGER in goals


def test_low_energy_creates_energy_goal():
    npc = create_npc()
    npc.energy = 20

    goals = GoalSystem().get_goals(npc)

    assert GoalType.RESTORE_ENERGY in goals


def test_low_money_creates_money_goal():
    npc = create_npc()
    npc.money = 10

    goals = GoalSystem().get_goals(npc)

    assert GoalType.EARN_MONEY in goals


def test_normal_state_has_no_urgent_goals():
    npc = create_npc()
    npc.hunger = 20
    npc.energy = 80
    npc.money = 50

    goals = GoalSystem().get_goals(npc)

    assert goals == []