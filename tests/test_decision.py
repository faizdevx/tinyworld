from WORLD.AI.action import ActionType
from WORLD.AI.decision import DecisionSystem
from WORLD.NPCs.npc import NPC
from WORLD.world import World
from WORLD.AI.action import ActionType

def create_npc(
    name="Rahul",
    location="Village Farm",
) -> NPC:
    return NPC(
        name=name,
        role="farmer",
        money=50,
        home="House 1",
        location=location,
    )


def test_high_hunger_and_no_food_choose_shop():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)

    rahul.hunger = 85
    rahul.energy = 20
    rahul.food = 0
    rahul.money = 50

    decision = DecisionSystem().decide(rahul, world)

    assert ActionType.SHOP in decision.scores
    assert ActionType.SLEEP in decision.scores

    assert decision.chosen_action == ActionType.SHOP


def test_food_and_high_hunger_choose_eat():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)

    rahul.hunger = 85
    rahul.energy = 50
    rahul.food = 1
    rahul.money = 50

    decision = DecisionSystem().decide(rahul, world)

    assert ActionType.EAT in decision.scores
    assert decision.chosen_action == ActionType.EAT


def test_low_energy_and_moderate_hunger_choose_sleep():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)

    rahul.hunger = 40
    rahul.energy = 20
    rahul.food = 0
    rahul.money = 50
    rahul.location = rahul.home

    decision = DecisionSystem().decide(rahul, world)

    assert decision.chosen_action == ActionType.SLEEP


def test_same_npc_can_make_different_decisions_after_state_changes():
    world = World()

    rahul = create_npc()

    world.add_npc(rahul)

    decision_system = DecisionSystem()

    # First state:
    # hungry + no food + enough money
    rahul.hunger = 85
    rahul.energy = 70
    rahul.food = 0
    rahul.money = 50

    first_decision = decision_system.decide(rahul, world)

    assert first_decision.chosen_action == ActionType.SHOP

    # State changes:
    # Rahul now owns food.
    rahul.food = 1

    second_decision = decision_system.decide(rahul, world)

    assert second_decision.chosen_action == ActionType.EAT


def test_low_energy_at_work_prefers_sleep():
    world = World()

    rahul = create_npc(
        location="Village Farm",
    )

    world.add_npc(rahul)

    rahul.energy = 20
    rahul.hunger = 20
    rahul.food = 0
    rahul.money = 50

    decision = DecisionSystem().decide(rahul, world)

    assert decision.scores[ActionType.SLEEP] > decision.scores[ActionType.WORK]
    assert decision.chosen_action == ActionType.SLEEP