from WORLD.AI.goal import GoalType
from WORLD.AI.goal_system import GoalSystem
from WORLD.NPCs.npc import NPC
from WORLD.world import World
from WORLD.AI.goal import Goal, GoalType

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


def test_nearby_npc_creates_social_goal():
    world = World()

    rahul = create_npc()

    ali = NPC(
        name="Ali",
        role="shopkeeper",
        money=50,
        home="House 1",
        location="House 1",
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    goals = GoalSystem().get_goals(
        rahul,
        world,
    )

    assert GoalType.SOCIALIZE in goals



def test_persistent_goal_can_be_created():
    goal = Goal(
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        created_day=4,
    )

    assert goal.goal_type == GoalType.EARN_MONEY
    assert goal.priority == 60
    assert goal.created_day == 4
    assert goal.deadline_day is None
    assert goal.progress == 0.0


def test_persistent_goal_can_have_deadline():
    goal = Goal(
        goal_type=GoalType.BUILD_RELATIONSHIP,
        priority=70,
        created_day=4,
        deadline_day=10,
    )

    assert goal.deadline_day == 10


def test_persistent_goal_tracks_progress():
    goal = Goal(
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        created_day=4,
        progress=30.0,
    )

    assert goal.progress == 30.0


def test_highest_priority_goal_is_selected():
    system = GoalSystem()

    goals = [
        Goal(
            goal_type=GoalType.EARN_MONEY,
            priority=60,
            created_day=1,
        ),
        Goal(
            goal_type=GoalType.BUILD_RELATIONSHIP,
            priority=80,
            created_day=1,
        ),
    ]

    selected = system.select_highest_priority(
        goals,
        current_day=1,
    )

    assert selected.goal_type == GoalType.BUILD_RELATIONSHIP


def test_deadline_increases_effective_priority():
    system = GoalSystem()

    goal = Goal(
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        created_day=1,
        deadline_day=3,
    )

    assert system.effective_priority(goal, 1) == 70
    assert system.effective_priority(goal, 2) == 80


def test_expired_goal_is_not_selected():
    system = GoalSystem()

    goal = Goal(
        goal_type=GoalType.EARN_MONEY,
        priority=100,
        created_day=1,
        deadline_day=3,
    )

    selected = system.select_highest_priority(
        [goal],
        current_day=4,
    )

    assert selected is None