from WORLD.Simulation.simulation import Simulation
from WORLD.NPCs.npc import NPC
from WORLD.world import World
from WORLD.Village.village import Village


def create_npc(
    name,
    location="House 1",
    money=0,
    food=0,
    hunger=80,
    reputation=0,
):
    return NPC(
        name=name,
        role="worker",
        money=money,
        home="House 1",
        location=location,
        food=food,
        hunger=hunger,
        reputation=reputation,
    )


def test_emergence_works_through_simulation_pipeline():
    world = World()

    rahul = create_npc(
        name="Rahul",
        money=0,
        food=0,
        hunger=80,
        reputation=-45,
    )

    ali = create_npc(
        name="Ali",
        money=50,
        food=1,
        hunger=20,
        reputation=0,
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    rahul.change_relationship(ali, 50)
    ali.change_relationship(rahul, 50)

    world.shop.food = 0
    world.shop.food_price = 5

    simulation = Simulation(world)

    simulation.tick()

    # Rahul needed help and Ali had food.
    assert rahul.food == 1
    assert ali.food == 0

    # Ali was the donor.
    assert ali.reputation == 5

    # Cooperation must improve the relationship.
    assert rahul.get_relationship(ali) > 50
    assert ali.get_relationship(rahul) > 50

    # Both NPCs remember the cooperation.
    assert any(
        memory.event == "Received food from Ali"
        for memory in rahul.memories
    )

    assert any(
        memory.event == "Gave food to Rahul"
        for memory in ali.memories
    )


def test_low_reputation_blocks_future_cooperation():
    world = World()

    rahul = create_npc(
        name="Rahul",
        money=0,
        food=0,
        hunger=80,
        reputation=-50,
    )

    ali = create_npc(
        name="Ali",
        money=0,
        food=0,
        hunger=80,
        reputation=0,
    )

    world.add_npc(rahul)
    world.add_npc(ali)

    rahul.change_relationship(ali, 46)
    ali.change_relationship(rahul, 46)

    world.shop.food = 0
    world.shop.food_price = 5

    simulation = Simulation(world)

    simulation.tick()

    # Rahul has reputation -50, so cooperation requires
    # relationship >= 50.
    #
    # Even though the relationship starts at 46, the NPCs
    # are also socially interacting during the simulation.
    #
    # We therefore verify the actual consequence instead:
    # Rahul must still fail to receive food because his
    # relationship remains below the cooperation threshold
    # after the tick.
    assert rahul.food == 0

    # Both NPCs had no food, were hungry, and could not
    # afford the shop price, so conflict should occur.
    assert rahul.reputation == -55
    assert ali.reputation == -5

    assert rahul.get_relationship(ali) < 46
    assert ali.get_relationship(rahul) < 46

    # Conflict leaves negative memories.
    assert any(
        memory.event == "Argued with Ali"
        for memory in rahul.memories
    )

    assert any(
        memory.event == "Argued with Rahul"
        for memory in ali.memories
    )


def test_random_environment_events_are_disabled_by_default():
    world = World()

    assert world.environment_system.random_events_enabled is False


def test_same_seed_produces_same_drought_events():
    world_a = World(seed=99)
    world_b = World(seed=99)

    world_a.environment_system.random_events_enabled = True
    world_b.environment_system.random_events_enabled = True

    Simulation(world_a).run(72)
    Simulation(world_b).run(72)

    drought_events_a = [
        event.event_type
        for event in world_a.event_log.events
        if event.event_type in {
            "DROUGHT_STARTED",
            "DROUGHT_ENDED",
        }
    ]

    drought_events_b = [
        event.event_type
        for event in world_b.event_log.events
        if event.event_type in {
            "DROUGHT_STARTED",
            "DROUGHT_ENDED",
        }
    ]

    assert drought_events_a == drought_events_b


def test_different_seed_can_produce_different_drought_outcome():
    world_a = World(seed=42)
    world_b = World(seed=99)

    world_a.environment_system.random_events_enabled = True
    world_b.environment_system.random_events_enabled = True

    Simulation(world_a).run(72)
    Simulation(world_b).run(72)

    started_a = [
        event
        for event in world_a.event_log.events
        if event.event_type == "DROUGHT_STARTED"
    ]

    started_b = [
        event
        for event in world_b.event_log.events
        if event.event_type == "DROUGHT_STARTED"
    ]

    assert len(started_a) != len(started_b)


def test_simulation_updates_environment():
    world = World(seed=99)

    world.environment_system.random_events_enabled = True

    assert world.environment_system.drought_active is False

    Simulation(world).tick()

    assert world.clock.hour == 9
    assert world.environment_system.drought_active is True


def run_village(seed):
    village = Village()
    world = village.create()

    # Village.create() should provide the project's actual
    # NPC/world setup:
    # 10 NPCs
    # 2 farmers
    # 1 shopkeeper
    # 7 workers
    # starting food: 20
    # starting money: ₹500

    world.rng = world.rng.__class__(seed)

    simulation = Simulation(world)
    simulation.run(72)

    return world


def test_multi_day_simulation_completes():
    world = run_village(42)

    assert world.clock.day >= 3


def test_same_seed_produces_same_state():
    world_a = run_village(42)
    world_b = run_village(42)

    assert world_a.food.quantity == world_b.food.quantity
    assert world_a.shop.food == world_b.shop.food
    assert world_a.shop.food_price == world_b.shop.food_price

    for npc_a, npc_b in zip(world_a.npcs, world_b.npcs):
        assert npc_a.money == npc_b.money
        assert npc_a.food == npc_b.food
        assert npc_a.energy == npc_b.energy
        assert npc_a.hunger == npc_b.hunger
        assert npc_a.reputation == npc_b.reputation
        relationships_a = {
                 other.name: npc_a.get_relationship(other)
                 for other in world_a.npcs
                 if other is not npc_a
                      }

        relationships_b = {
               other.name: npc_b.get_relationship(other)
               for other in world_b.npcs
               if other is not npc_b
                }

        assert relationships_a == relationships_b


def test_different_seeds_can_produce_different_state():
    world_a = run_village(42)
    world_b = run_village(1)

    state_a = (
        world_a.food.quantity,
        world_a.shop.food,
        world_a.shop.food_price,
    )

    state_b = (
        world_b.food.quantity,
        world_b.shop.food,
        world_b.shop.food_price,
    )

    assert state_a != state_b