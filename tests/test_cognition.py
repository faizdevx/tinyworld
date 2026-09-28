from WORLD.world import World
from WORLD.NPCs.npc import NPC
from WORLD.AI.goal import GoalType


def test_long_term_goal_survives_multiple_simulation_days():
    world = World(seed=42)

    npc = NPC(
        name="Rahul",
        role="worker",
        money=10,
        home="Home",
        location="Home",
    )

    world.add_npc(npc)

    goal = world.agent_system.goal_system.create_long_term_goal(
        npc=npc,
        goal_type=GoalType.EARN_MONEY,
        priority=60,
        current_day=world.clock.day,
    )

    initial_day = world.clock.day

    world.clock.hour = 0

    from WORLD.Simulation.simulation import Simulation

    simulation = Simulation(world)
    simulation.run(48)

    assert world.clock.day > initial_day
    assert goal in npc.long_term_goals
    assert goal.progress == 0.0