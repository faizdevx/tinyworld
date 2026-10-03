from dataclasses import FrozenInstanceError

import pytest

from WORLD.AI.action import ActionType
from WORLD.AI.action_executor import ActionExecutor
from WORLD.Entities.entity import WorldEntity
from WORLD.Events.engine import (
    ConsequenceEngine,
    EventEngine,
    EventResolver,
    EventValidator,
)
from WORLD.Events.event import (
    EventProposal,
    EventSource,
    EventValidationResult,
    WorldEvent,
)
from WORLD.Interventions import GodIntervention
from WORLD.NPCs.npc import NPC
from WORLD.world import World


def create_npc(world, *, name="Rahul", location=None, money=20):
    npc = NPC(
        name=name,
        role="villager",
        money=money,
        home=world.shop.name,
        location=location or world.shop.name,
    )
    world.add_npc(npc)
    return npc


def shop_proposal(npc, *, quantity=1):
    return EventProposal(
        actor=f"npc:{npc.name}",
        action_type=ActionType.SHOP,
        target="resource:Food",
        properties={"quantity": quantity},
        source=EventSource.NPC,
    )


def test_event_proposal_is_immutable_and_does_not_mutate_world():
    world = World()
    rahul = create_npc(world)
    proposal = shop_proposal(rahul)
    initial = (rahul.money, rahul.food, world.shop.money, world.shop.food)

    validation = EventValidator().validate(world, proposal)

    assert validation.success is True
    assert (rahul.money, rahul.food, world.shop.money, world.shop.food) == initial
    with pytest.raises(FrozenInstanceError):
        proposal.actor = "npc:Ali"
    with pytest.raises(TypeError):
        proposal.properties["quantity"] = 3

    nested = EventProposal(
        actor="npc:Rahul",
        action_type=ActionType.SHOP,
        properties={"request": {"quantity": 1}},
    )
    with pytest.raises(TypeError):
        nested.properties["request"]["quantity"] = 2


def test_successful_purchase_resolves_then_applies_and_records_event():
    world = World()
    rahul = create_npc(world, money=20)

    result = world.event_engine.process(world, shop_proposal(rahul))

    assert result.success is True
    assert result.event.event_type == "PURCHASE"
    assert result.event.properties == {
        "item": "Food",
        "quantity": 1,
        "unit_price": 5,
        "price": 5,
    }
    assert "Rahul bought 1 Food for 5" in result.event.description
    assert (rahul.money, rahul.food, world.shop.money, world.shop.food) == (
        15,
        1,
        105,
        19,
    )
    assert world.event_log.events == [result.event]
    assert result.event.sequence == 1


def test_failed_purchase_is_rejected_without_event_or_mutation():
    world = World()
    rahul = create_npc(world, money=2)
    before = (rahul.money, rahul.food, world.shop.money, world.shop.food)

    result = world.event_engine.process(world, shop_proposal(rahul))

    assert result.success is False
    assert "cannot afford" in result.reason
    assert (rahul.money, rahul.food, world.shop.money, world.shop.food) == before
    assert world.event_log.events == []


def test_wrong_location_and_empty_stock_purchases_are_rejected():
    world = World()
    rahul = create_npc(world, location="Settlement")

    wrong_location = world.event_engine.process(world, shop_proposal(rahul))
    assert wrong_location.success is False
    assert "not at the shop" in wrong_location.reason
    assert rahul.location == "Settlement"

    rahul.move_to(world.shop.name)
    world.shop.food = 0
    empty_stock = world.event_engine.process(world, shop_proposal(rahul))

    assert empty_stock.success is False
    assert "insufficient Food" in empty_stock.reason
    assert rahul.money == 20
    assert rahul.food == 0
    assert world.event_log.events == []


def test_invalid_quantity_and_unknown_npc_are_rejected():
    world = World()
    rahul = create_npc(world)

    invalid_quantity = world.event_engine.process(
        world,
        shop_proposal(rahul, quantity=0),
    )
    unknown_actor = world.event_engine.process(
        world,
        EventProposal(
            actor="npc:Missing",
            action_type=ActionType.SHOP,
            target="resource:Food",
        ),
    )

    assert invalid_quantity.success is False
    assert unknown_actor.success is False
    assert world.shop.food == 20
    assert world.event_log.events == []


def test_resolver_rejects_invalid_validation_result():
    world = World()
    rahul = create_npc(world)
    proposal = shop_proposal(rahul)

    with pytest.raises(ValueError):
        EventResolver().resolve(
            world,
            proposal,
            EventValidationResult(False, "rejected"),
        )


def test_system_event_proposal_resolves_through_world_event_log():
    world = World()
    proposal = EventProposal(
        actor="system:environment",
        action_type="system_event",
        target="event:season_change",
        properties={
            "event_type": "SEASON_CHANGE",
            "description": "The season changed.",
        },
        source=EventSource.SYSTEM,
    )

    result = world.event_engine.process(world, proposal)

    assert result.success is True
    assert result.event.event_type == "SEASON_CHANGE"
    assert result.event.description == "The season changed."
    assert world.event_log.events == [result.event]


def test_event_log_assigns_sequences_to_legacy_world_events():
    world = World()
    world.event_log.add(
        WorldEvent(
            day=1,
            hour=8,
            event_type="LEGACY_EVENT",
            actor="System",
            target=None,
            description="A legacy system event.",
        )
    )

    assert world.event_log.events[0].sequence == 1


def test_action_executor_uses_event_pipeline_for_purchase():
    world = World()
    rahul = create_npc(world)

    success = ActionExecutor().execute(rahul, ActionType.SHOP, world)

    assert success is True
    assert len(world.event_log.events) == 1
    assert world.event_log.events[0].event_type == "PURCHASE"


def test_god_spawn_becomes_world_event_then_observation():
    world = World()
    nearby = NPC(
        name="Rahul",
        role="villager",
        money=20,
        home="Settlement",
        location="Forest",
    )
    distant = NPC(
        name="Ali",
        role="villager",
        money=20,
        home="Settlement",
        location="Settlement",
    )
    world.add_npc(nearby)
    world.add_npc(distant)

    result = world.intervention_engine.apply(
        world,
        GodIntervention(
            operation="spawn",
            target="entity:Foreign Army",
            properties={
                "entity_type": "army",
                "location": "Forest",
                "size": 500,
            },
        ),
    )

    assert result.success is True
    assert len(world.entities) == 1
    assert world.entities[0].properties["size"] == 500
    assert len(world.event_log.events) == 1
    assert world.event_log.events[0].event_type == "SPAWN"
    assert world.intervention_history[-1].intervention.target == "entity:Foreign Army"
    assert world.observation_system.observe(world, nearby)[0].facts["perceived_size"] == "large"
    assert world.observation_system.observe(world, distant) == []
    assert nearby.memories == []
    assert distant.memories == []


def test_god_resource_change_is_causal_and_audit_is_separate():
    world = World()
    original_resource = world.food

    result = world.intervention_engine.apply(
        world,
        GodIntervention(
            operation="change_resource",
            target="resource:Food",
            value=-95,
            visibility="god_only",
        ),
    )

    assert result.success is True
    assert world.food.quantity == 5
    assert world.resources["Food"] is original_resource
    assert [event.event_type for event in world.event_log.events] == [
        "RESOURCE_CHANGE",
    ]
    assert len(world.intervention_history) == 1
    assert world.intervention_history[0].after == 5


def test_stale_purchase_proposal_fails_after_stock_is_removed():
    world = World()
    rahul = create_npc(world)
    proposal = shop_proposal(rahul)

    validation_before = world.event_engine.validator.validate(world, proposal)
    assert validation_before.success is True
    world.shop.food = 0
    before = (rahul.money, rahul.food, world.shop.money, world.shop.food)

    execution = world.event_engine.process(world, proposal)

    assert execution.success is False
    assert (rahul.money, rahul.food, world.shop.money, world.shop.food) == before
    assert world.event_log.events == []


def test_multiple_events_have_deterministic_causal_sequence():
    world = World()
    rahul = create_npc(world)
    proposal = shop_proposal(rahul)

    first = world.event_engine.process(world, proposal)
    second = world.event_engine.process(world, proposal)

    assert first.success is True
    assert second.success is True
    assert [event.sequence for event in world.event_log.events] == [1, 2]
    assert [event.event_type for event in world.event_log.events] == [
        "PURCHASE",
        "PURCHASE",
    ]


def test_spawn_rejection_does_not_create_entity_or_world_event():
    world = World()

    result = world.intervention_engine.apply(
        world,
        GodIntervention(
            operation="spawn",
            target="entity:Broken Army",
            properties={"unsupported": True},
        ),
    )

    assert result.success is False
    assert world.entities == []
    assert world.event_log.events == []
    assert len(world.intervention_history) == 1


def test_event_log_is_not_broadcast_as_universal_observation():
    world = World()
    world.event_log.add(
        __import__("WORLD.Events.event", fromlist=["WorldEvent"]).WorldEvent(
            day=world.clock.day,
            hour=world.clock.hour,
            event_type="ARMY_ARRIVAL",
            actor="System",
            target="Forest",
            description="An army arrived.",
        )
    )
    distant = NPC(
        name="Ali",
        role="villager",
        money=10,
        home="Settlement",
        location="Settlement",
    )

    assert len(world.event_log.events) == 1
    assert world.observation_system.observe(world, distant) == []
