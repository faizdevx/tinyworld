import pytest

from WORLD.AI.observation import (
    Observation,
    ObservationSystem,
    ObservationType,
)
from WORLD.Entities.entity import WorldEntity
from WORLD.Events.event import WorldEvent
from WORLD.Genesis.generator import WorldGenerator
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Interventions import GodIntervention, InterventionOperation
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def make_npc(name, location):
    return NPC(
        name=name,
        role="villager",
        money=50,
        home="Settlement",
        location=location,
    )


def make_army(location="Forest", size=500):
    return WorldEntity(
        name="Foreign Army",
        entity_type="army",
        location=location,
        properties={"size": size},
    )


def test_observation_is_immutable_and_value_based():
    observation = Observation(
        observer="Rahul",
        subject="Foreign Army",
        description="A large group was seen.",
        location="Forest",
        distance=0,
        source="world_entity",
        observation_type=ObservationType.VISUAL,
        timestamp=(1, 8),
        facts={"perceived_size": "large"},
    )

    with pytest.raises((AttributeError, TypeError)):
        observation.description = "changed"
    with pytest.raises(TypeError):
        observation.facts["size"] = 500


def test_observation_snapshot_does_not_change_with_world_entity():
    world = World()
    army = make_army()
    world.add_entity(army)
    observer = make_npc("Rahul", "Forest")
    system = ObservationSystem()

    observations = system.observe(world, observer)
    army.properties["size"] = 1000

    assert observations[0].facts["perceived_size"] == "large"
    assert not hasattr(observations[0], "world")
    assert not hasattr(observations[0], "target")


def test_visibility_is_location_specific():
    world = World()
    world.add_entity(make_army())
    system = ObservationSystem()
    nearby = make_npc("Rahul", "Forest")
    distant = make_npc("Sara", "Settlement")

    assert system.observe(world, nearby)
    assert system.observe(world, distant) == []
    assert system.visible(world, nearby, world.entities[0]) is True
    assert system.visible(world, distant, world.entities[0]) is False


def test_hearing_is_separate_from_visual_range():
    world = World()
    world.add_entity(make_army())
    system = ObservationSystem(vision_range=0, hearing_range=1)
    road_observer = make_npc("Sara", "Road")

    observations = system.observe(world, road_observer)

    assert len(observations) == 1
    assert observations[0].observation_type is ObservationType.AUDITORY
    assert observations[0].distance == 1


def test_unknown_locations_are_safely_unobservable():
    world = World()
    world.add_entity(make_army(location="Unknown Place"))
    system = ObservationSystem()
    observer = make_npc("Rahul", "Settlement")

    assert system.distance("Settlement", "Unknown Place") is None
    assert system.observe(world, observer) == []


def test_attention_limit_is_deterministic():
    world = World()
    for name in ("Zulu", "Alpha", "Middle"):
        world.add_entity(
            WorldEntity(
                name=name,
                entity_type="landmark",
                location="Forest",
            )
        )
    observer = make_npc("Rahul", "Forest")
    system = ObservationSystem(attention_limit=2)

    first = system.observe(world, observer)
    second = system.observe(world, observer)

    assert [observation.subject for observation in first] == [
        "Alpha",
        "Middle",
    ]
    assert first == second


def test_world_events_are_filtered_by_location():
    world = World()
    world.event_log.add(
        WorldEvent(
            day=1,
            hour=8,
            event_type="ARMY_MOVEMENT",
            actor="World",
            target="Forest",
            description="Movement was heard near the forest.",
        )
    )
    system = ObservationSystem()

    nearby = system.observe(world, make_npc("Rahul", "Forest"))
    distant = system.observe(world, make_npc("Sara", "Settlement"))

    assert len(nearby) == 1
    assert nearby[0].source == "world_event"
    assert distant == []


def test_phase10_spawned_army_is_observable_only_nearby():
    world = WorldGenerator().generate(WorldScenario(population=0))
    result = world.intervention_engine.apply(
        world,
        GodIntervention(
            operation=InterventionOperation.SPAWN,
            target="entity:Foreign Army",
            properties={
                "entity_type": "army",
                "location": "Forest",
                "size": 500,
            },
        ),
    )
    system = ObservationSystem()
    outside = make_npc("Ali", "Settlement")
    nearby = make_npc("Rahul", "Forest")

    outside_observations = system.observe(world, outside)
    nearby_observations = system.observe(world, nearby)

    assert result.success is True
    assert len(world.entities) == 1
    assert outside_observations == []
    assert len(nearby_observations) == 1
    assert nearby_observations[0].subject == "Foreign Army"
    assert nearby_observations[0].facts["perceived_size"] == "large"
    assert 500 not in nearby_observations[0].facts.values()
    assert world.intervention_history


def test_brain_receives_npc_specific_observation_snapshots():
    world = World()
    world.add_entity(make_army())
    nearby = make_npc("Rahul", "Forest")
    outside = make_npc("Ali", "Settlement")
    world.add_npc(nearby)
    world.add_npc(outside)

    nearby.brain.observe(world)
    outside.brain.observe(world)

    assert len(nearby.observations) == 1
    assert outside.observations == ()
    assert nearby.observations[0].observer == "Rahul"
    assert nearby.observations[0].subject == "Foreign Army"


def test_cognition_view_excludes_unfiltered_world_collections():
    world = World()
    world.add_entity(make_army())
    nearby = make_npc("Rahul", "Forest")
    outside = make_npc("Ali", "Settlement")
    world.add_npc(nearby)
    world.add_npc(outside)

    view = world.observation_system.cognition_view(world, nearby)

    assert view.npcs == ()
    assert not hasattr(view, "resources")
    assert not hasattr(view, "entities")
    assert not hasattr(view, "factions")
    assert not hasattr(view, "intervention_history")


def test_observations_do_not_automatically_create_memory_or_knowledge():
    world = World()
    world.add_entity(make_army())
    nearby = make_npc("Rahul", "Forest")
    world.add_npc(nearby)

    nearby.brain.observe(world)

    assert nearby.observations
    assert nearby.memories == []
    assert nearby.knowledge.for_subject("Foreign Army") == []


def test_god_audit_is_not_an_observation_source():
    world = World()
    result = world.intervention_engine.apply(
        world,
        GodIntervention(
            operation="change_resource",
            target="resource:Food",
            value=-95,
            visibility="god_only",
        ),
    )
    observer = make_npc("Rahul", "Settlement")

    observations = world.observation_system.observe(world, observer)

    assert result.success is True
    assert world.food.quantity == 5
    assert observations == []
    assert observer.memories == []
    assert observer.knowledge.for_subject("Food") == []


def test_world_truth_can_exceed_npc_knowledge():
    world = World()
    world.add_entity(make_army(size=500))
    outside = make_npc("Ali", "Settlement")
    nearby = make_npc("Rahul", "Forest")

    outside_observations = world.observation_system.observe(world, outside)
    nearby_observations = world.observation_system.observe(world, nearby)

    assert world.entities[0].properties["size"] == 500
    assert outside_observations == []
    assert nearby_observations[0].facts["perceived_size"] == "large"
    assert nearby_observations[0].facts.get("size") is None


def test_world_entity_update_changes_future_observations_without_live_alias():
    world = World()
    world.add_entity(make_army(size=10))
    observer = make_npc("Rahul", "Forest")

    before = world.observation_system.observe(world, observer)[0]
    result = world.intervention_engine.apply(
        world,
        GodIntervention(
            operation="update",
            target="entity:Foreign Army",
            properties={"properties": {"size": 500}},
        ),
    )
    after = world.observation_system.observe(world, observer)[0]

    assert result.success is True
    assert before.facts["perceived_size"] == "small"
    assert after.facts["perceived_size"] == "large"
    assert before.facts["perceived_size"] != after.facts["perceived_size"]
