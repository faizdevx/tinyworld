import pytest

from WORLD.Buildings.buildings import Building
from WORLD.Entities.entity import WorldEntity
from WORLD.Factions.faction import Faction
from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Interventions import (
    GodIntervention,
    InterventionEngine,
    InterventionOperation,
    InterventionVisibility,
    TargetResolver,
)
from WORLD.NPCs.npc import NPC
from WORLD.Simulation.simulation import Simulation
from WORLD.world import World


ALL_OPERATIONS = tuple(InterventionOperation)


def apply(world, **kwargs):
    return InterventionEngine().apply(world, GodIntervention(**kwargs))


def test_intervention_model_accepts_all_operations_and_freezes_command():
    for operation in ALL_OPERATIONS:
        value = 0 if operation == InterventionOperation.ADVANCE_TIME else None
        if operation == InterventionOperation.CHANGE_RESOURCE:
            value = 0
        intervention = GodIntervention(
            operation=operation,
            target="resource:Food",
            value=value,
        )
        assert intervention.operation is operation
        assert intervention.visibility is InterventionVisibility.GOD_ONLY

    intervention = GodIntervention(
        operation="change_resource",
        target="resource:Food",
        properties={"source": "god"},
        value=-1,
        visibility="world",
    )

    assert intervention.visibility is InterventionVisibility.WORLD
    assert intervention.properties == {"source": "god"}
    with pytest.raises(Exception):
        intervention.target = "resource:Wood"


def test_intervention_model_rejects_invalid_structure():
    with pytest.raises(ValueError):
        GodIntervention(operation="unknown", target="resource:Food")
    with pytest.raises(ValueError):
        GodIntervention(operation="update", target="")
    with pytest.raises(TypeError):
        GodIntervention(
            operation="update",
            target="resource:Food",
            properties=[],
        )
    with pytest.raises(ValueError):
        GodIntervention(
            operation="advance_time",
            target="world:clock.hour",
            value=-1,
        )


def test_result_distinguishes_changed_and_unchanged_success():
    world = World()

    unchanged = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=0,
    )
    failed = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=-101,
    )

    assert unchanged.success is True
    assert unchanged.changed is False
    assert failed.success is False
    assert failed.changed is False


def test_change_resource_uses_existing_resource_and_preserves_food_identity():
    world = World()
    resource = world.food

    decrease = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=-95,
    )
    increase = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=20,
    )

    assert decrease.success is True
    assert increase.success is True
    assert world.food.quantity == 25
    assert world.resources["Food"] is resource


def test_failed_resource_change_is_atomic():
    world = World()

    result = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=-101,
    )

    assert result.success is False
    assert world.food.quantity == 100


def test_target_resolver_supports_explicit_namespaces():
    world = World()
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )
    world.add_npc(npc)
    world.add_building(Building(name="Workshop", building_type="workshop"))
    world.add_entity(WorldEntity(name="Forest", entity_type="forest"))
    world.add_faction(Faction(name="Regional Ruler", faction_type="ruler"))
    resolver = TargetResolver()

    assert resolver.resolve(world, "resource:Food").value is world.food
    assert resolver.resolve(world, "npc:Rahul").value is npc
    assert resolver.resolve(world, "building:Workshop").value.name == "Workshop"
    assert resolver.resolve(world, "entity:Forest").value.name == "Forest"
    assert resolver.resolve(world, "faction:Regional Ruler").value.name == "Regional Ruler"
    assert resolver.resolve(world, "world:metadata.climate").key == "climate"


def test_target_resolver_rejects_malformed_or_unknown_targets():
    world = World()
    resolver = TargetResolver()

    for target in ("Food", "resource:", ":Food", "resource:Food:extra"):
        with pytest.raises((TypeError, ValueError)):
            resolver.resolve(world, target)

    with pytest.raises(ValueError):
        resolver.resolve(world, "resource:Missing")
    with pytest.raises(ValueError):
        resolver.resolve(world, "python:__class__")


def test_update_resource_metadata_and_npc_are_controlled():
    world = World()
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )
    world.add_npc(npc)

    resource_result = apply(
        world,
        operation="update",
        target="resource:Food",
        properties={"quantity": 20},
    )
    metadata_result = apply(
        world,
        operation="update",
        target="world:metadata.climate",
        value="cold",
    )
    npc_result = apply(
        world,
        operation="update",
        target="npc:Rahul",
        properties={"money": 100, "energy": 80},
    )

    assert resource_result.success is True
    assert world.food.quantity == 20
    assert metadata_result.success is True
    assert world.metadata["climate"] == "cold"
    assert npc_result.success is True
    assert npc.money == 100
    assert npc.energy == 80


def test_update_rejects_invalid_field_and_partial_mutation():
    world = World()
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )
    world.add_npc(npc)

    invalid_field = apply(
        world,
        operation="update",
        target="npc:Rahul",
        properties={"brain": "hidden"},
    )
    partial = apply(
        world,
        operation="update",
        target="npc:Rahul",
        properties={"money": 100, "location": ""},
    )

    assert invalid_field.success is False
    assert partial.success is False
    assert npc.money == 50
    assert npc.location == "House 1"


def test_create_and_remove_generic_world_objects():
    world = World()

    entity = apply(
        world,
        operation="create",
        target="entity:Caravan",
        properties={"entity_type": "caravan"},
    )
    faction = apply(
        world,
        operation="create",
        target="faction:Merchant Guild",
        properties={"faction_type": "guild"},
    )
    building = apply(
        world,
        operation="create",
        target="building:Workshop",
        properties={"building_type": "workshop", "money": 10},
    )
    remove = apply(
        world,
        operation="remove",
        target="entity:Caravan",
    )
    missing = apply(
        world,
        operation="remove",
        target="entity:Caravan",
    )

    assert entity.success is True
    assert faction.success is True
    assert building.success is True
    assert world.factions[0].faction_type == "guild"
    assert world.buildings[0].money == 10
    assert remove.success is True
    assert world.entities == []
    assert missing.success is False


def test_failed_create_is_atomic():
    world = World()

    result = apply(
        world,
        operation="create",
        target="entity:Caravan",
        properties={
            "entity_type": "caravan",
            "unsupported": True,
        },
    )

    assert result.success is False
    assert world.entities == []


def test_create_and_spawn_npc_use_normal_world_initialization():
    world = World()

    created = apply(
        world,
        operation="spawn",
        target="npc:Caravan Guard",
        properties={
            "role": "guard",
            "home": "Caravan",
            "location": "Caravan",
            "money": 10,
        },
    )

    assert created.success is True
    assert len(world.npcs) == 1
    assert world.npcs[0].brain is not None
    assert world.npcs[0].role == "guard"

    despawned = apply(
        world,
        operation="despawn",
        target="npc:Caravan Guard",
    )

    assert despawned.success is True
    assert world.npcs == []


def test_move_uses_existing_npc_location_api():
    world = World()
    npc = NPC(
        name="Rahul",
        role="farmer",
        money=50,
        home="House 1",
        location="House 1",
    )
    world.add_npc(npc)

    moved = apply(
        world,
        operation="move",
        target="npc:Rahul",
        properties={"location": "Forest"},
    )
    invalid = apply(
        world,
        operation="move",
        target="npc:Rahul",
        properties={"location": ""},
    )

    assert moved.success is True
    assert npc.location == "Forest"
    assert invalid.success is False
    assert npc.location == "Forest"


def test_trigger_event_reuses_existing_event_log():
    world = World()

    result = apply(
        world,
        operation="trigger_event",
        target="event:drought",
        properties={"description": "Dry season began."},
    )

    assert result.success is True
    assert len(world.event_log.events) == 1
    assert world.event_log.events[0].event_type == "DROUGHT"
    assert world.event_log.events[0].description == "Dry season began."


def test_change_environment_uses_existing_environment_system():
    world = World()

    start = apply(
        world,
        operation="change_environment",
        target="environment:drought",
        value=True,
    )
    climate = apply(
        world,
        operation="change_environment",
        target="environment:climate",
        value="cold",
    )
    end = apply(
        world,
        operation="change_environment",
        target="environment:drought",
        value=False,
    )

    assert start.success is True
    assert climate.success is True
    assert end.success is True
    assert world.environment_system.drought_active is False
    assert world.metadata["climate"] == "cold"
    assert [event.event_type for event in world.event_log.events] == [
        "DROUGHT_STARTED",
        "DROUGHT_ENDED",
    ]


def test_change_rule_is_data_only_and_rejects_executable_values():
    world = World()

    result = apply(
        world,
        operation="change_rule",
        target="rule:food_price_override",
        value=9,
    )
    world_target = apply(
        world,
        operation="change_rule",
        target="world:rules.production_multiplier",
        value=0.5,
    )
    invalid = apply(
        world,
        operation="change_rule",
        target="rule:bad__rule",
        value=1,
    )
    executable = apply(
        world,
        operation="change_rule",
        target="rule:callable",
        value=lambda: None,
    )

    assert result.success is True
    assert world_target.success is True
    assert world.rules == {
        "food_price_override": 9,
        "production_multiplier": 0.5,
    }
    assert invalid.success is False
    assert executable.success is False


def test_update_rule_rejects_executable_values():
    world = World()

    result = apply(
        world,
        operation="update",
        target="rule:callable",
        properties={"value": lambda: None},
    )

    assert result.success is False
    assert world.rules == {}


def test_advance_time_uses_existing_clock():
    world = World()
    starting_time = (world.clock.day, world.clock.hour)

    result = apply(
        world,
        operation="advance_time",
        target="world:clock.hour",
        value=3,
    )
    unchanged = apply(
        world,
        operation="advance_time",
        target="world:clock.hour",
        value=0,
    )

    assert result.success is True
    assert result.changed is True
    assert (world.clock.day, world.clock.hour) != starting_time
    assert unchanged.success is True
    assert unchanged.changed is False


def test_god_only_intervention_is_not_npc_knowledge():
    world = WorldGenerator().generate(WorldScenario(population=1))
    npc = world.npcs[0]

    result = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=-95,
        visibility="god_only",
    )

    assert result.success is True
    assert world.food.quantity == 5
    assert npc.memories == []
    assert npc.knowledge.for_subject("Food") == []
    assert all("God" not in memory.event for memory in npc.memories)
    assert world.intervention_history[-1].intervention.visibility is (
        InterventionVisibility.GOD_ONLY
    )
    assert world.intervention_history[-1].result == result


def test_intervention_history_is_god_side_audit_data():
    world = World()

    result = apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=-10,
    )

    audit = world.intervention_history[-1]
    assert audit.result == result
    assert audit.before == 100
    assert audit.after == 90
    assert audit.day == world.clock.day
    assert audit.hour == world.clock.hour


def test_generated_world_continues_through_normal_simulation():
    world = WorldGenerator().generate(WorldScenario(population=2))
    apply(
        world,
        operation="change_resource",
        target="resource:Food",
        value=-95,
    )
    starting_hour = world.clock.hour

    Simulation(world).tick()

    assert world.food.quantity >= 0
    assert world.clock.hour == (starting_hour + 1) % 24


def test_intervention_sequence_is_deterministic():
    def run_sequence():
        world = World()
        apply(
            world,
            operation="change_resource",
            target="resource:Food",
            value=-20,
        )
        apply(
            world,
            operation="create",
            target="entity:Caravan",
            properties={"entity_type": "caravan"},
        )
        apply(
            world,
            operation="advance_time",
            target="world:clock.hour",
            value=2,
        )
        return (
            world.food.quantity,
            [(entity.name, entity.entity_type) for entity in world.entities],
            (world.clock.day, world.clock.hour),
        )

    assert run_sequence() == run_sequence()
