from collections.abc import Mapping
from typing import Any

from WORLD.Buildings.buildings import Building
from WORLD.Entities.entity import WorldEntity
from WORLD.Events.event import WorldEvent
from WORLD.Events.event import EventProposal, EventSource
from WORLD.Factions.faction import Faction
from WORLD.Interventions.models import (
    GodIntervention,
    InterventionAudit,
    InterventionOperation,
    InterventionResult,
)
from WORLD.Interventions.resolver import TargetResolution, TargetResolver
from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource


class InterventionEngine:
    def __init__(self, resolver: TargetResolver | None = None) -> None:
        self.resolver = resolver or TargetResolver()

    def apply(self, world, intervention: GodIntervention) -> InterventionResult:
        if not isinstance(intervention, GodIntervention):
            raise TypeError("intervention must be a GodIntervention")

        causal_operations = {
            InterventionOperation.CREATE,
            InterventionOperation.SPAWN,
            InterventionOperation.REMOVE,
            InterventionOperation.DESPAWN,
            InterventionOperation.MOVE,
            InterventionOperation.TRIGGER_EVENT,
            InterventionOperation.CHANGE_RESOURCE,
        }
        if intervention.operation in causal_operations:
            result, before, after = self._apply_as_event(
                world,
                intervention,
            )
            self._record(world, intervention, result, before, after)
            return result

        try:
            result, before, after = self._apply(world, intervention)
        except (TypeError, ValueError, KeyError) as exc:
            result = self._failure(intervention, str(exc))
            before = None
            after = None

        self._record(world, intervention, result, before, after)
        return result

    def _apply_as_event(self, world, intervention):
        properties = dict(intervention.properties)
        if intervention.operation == InterventionOperation.CHANGE_RESOURCE:
            properties["amount"] = intervention.value
        proposal = EventProposal(
            actor="god",
            action_type=intervention.operation.value,
            target=intervention.target,
            properties=properties,
            source=EventSource.GOD,
            timestamp=(world.clock.day, world.clock.hour),
        )
        processed = world.event_engine.process(world, proposal)
        if not processed.success:
            return (
                self._failure(intervention, processed.reason),
                None,
                None,
            )
        return (
            self._success(
                intervention,
                processed.reason,
                processed.before != processed.after
                or intervention.operation
                in {
                    InterventionOperation.CREATE,
                    InterventionOperation.SPAWN,
                    InterventionOperation.REMOVE,
                    InterventionOperation.DESPAWN,
                    InterventionOperation.TRIGGER_EVENT,
                },
            ),
            processed.before,
            processed.after,
        )

    def _apply(
        self,
        world,
        intervention: GodIntervention,
    ) -> tuple[InterventionResult, Any, Any]:
        operation = intervention.operation
        if operation == InterventionOperation.CHANGE_RESOURCE:
            return self._change_resource(world, intervention)
        if operation == InterventionOperation.UPDATE:
            return self._update(world, intervention)
        if operation in {
            InterventionOperation.CREATE,
            InterventionOperation.SPAWN,
        }:
            return self._create(world, intervention)
        if operation in {
            InterventionOperation.REMOVE,
            InterventionOperation.DESPAWN,
        }:
            return self._remove(world, intervention)
        if operation == InterventionOperation.MOVE:
            return self._move(world, intervention)
        if operation == InterventionOperation.TRIGGER_EVENT:
            return self._trigger_event(world, intervention)
        if operation == InterventionOperation.CHANGE_ENVIRONMENT:
            return self._change_environment(world, intervention)
        if operation == InterventionOperation.CHANGE_RULE:
            return self._change_rule(world, intervention)
        if operation == InterventionOperation.ADVANCE_TIME:
            return self._advance_time(world, intervention)
        raise ValueError(f"Unsupported operation: {operation.value}")

    def _change_resource(self, world, intervention):
        resolution = self.resolver.resolve(world, intervention.target)
        if resolution.namespace != "resource":
            raise ValueError("CHANGE_RESOURCE requires a resource target")
        resource: Resource = resolution.value
        before = resource.quantity
        amount = intervention.value
        if amount > 0:
            resource.add(amount)
        elif amount < 0 and not resource.consume(-amount):
            return self._failure(
                intervention,
                "resource quantity is insufficient",
            ), before, before
        after = resource.quantity
        return self._success(
            intervention,
            "resource changed",
            before != after,
        ), before, after

    def _update(self, world, intervention):
        resolution = self.resolver.resolve(world, intervention.target)
        updates = dict(intervention.properties)
        if intervention.value is not None:
            if updates:
                raise ValueError("UPDATE cannot combine value and properties")
            updates = {"value": intervention.value}
        if not updates:
            raise ValueError("UPDATE requires properties or value")

        before = self._snapshot(resolution)
        self._validate_updates(world, resolution, updates)
        self._apply_updates(world, resolution, updates)
        after = self._snapshot(resolution)
        return self._success(
            intervention,
            "target updated",
            before != after,
        ), before, after

    def _create(self, world, intervention):
        namespace, identifier = self.resolver.parse(intervention.target)
        if namespace not in {
            "resource",
            "npc",
            "building",
            "entity",
            "faction",
        }:
            raise ValueError("CREATE and SPAWN require a world object target")
        try:
            self.resolver.resolve(world, intervention.target)
        except ValueError as exc:
            if "Unknown" not in str(exc):
                raise
        else:
            raise ValueError(f"Target already exists: {intervention.target}")

        properties = dict(intervention.properties)
        allowed_properties = {
            "resource": {"name", "quantity"},
            "npc": {
                "name",
                "role",
                "money",
                "home",
                "location",
                "food",
                "energy",
                "hunger",
            },
            "building": {"name", "building_type", "money"},
            "entity": {
                "name",
                "entity_type",
                "location",
                "properties",
                "size",
            },
            "faction": {"name", "faction_type"},
        }
        unsupported = set(properties) - allowed_properties[namespace]
        if unsupported:
            raise ValueError(
                f"Unsupported creation properties: {sorted(unsupported)}"
            )
        name = properties.pop("name", identifier)
        if name != identifier:
            raise ValueError("target identifier must match object name")

        if namespace == "resource":
            created = Resource(
                name=name,
                quantity=self._int_property(properties, "quantity", 0),
            )
            world.resources[name] = created
        elif namespace == "building":
            created = Building(
                name=name,
                building_type=self._str_property(
                    properties,
                    "building_type",
                    "generic",
                ),
                money=self._int_property(properties, "money", 0),
            )
            world.add_building(created)
        elif namespace == "entity":
            location = properties.pop("location", None)
            entity_properties = properties.pop("properties", {})
            if not isinstance(entity_properties, Mapping):
                raise TypeError("entity properties must be a mapping")
            created = WorldEntity(
                name=name,
                entity_type=self._str_property(
                    properties,
                    "entity_type",
                    "generic",
                ),
                location=location,
                properties={
                    **dict(entity_properties),
                    **properties,
                },
            )
            world.add_entity(created)
            properties = {}
        elif namespace == "faction":
            created = Faction(
                name=name,
                faction_type=self._str_property(
                    properties,
                    "faction_type",
                    "generic",
                ),
            )
            world.add_faction(created)
        else:
            created = NPC(
                name=name,
                role=self._str_property(properties, "role", "villager"),
                money=self._int_property(properties, "money", 0),
                home=self._str_property(properties, "home", "Settlement"),
                location=self._str_property(
                    properties,
                    "location",
                    "Settlement",
                ),
                food=self._int_property(properties, "food", 0),
                energy=self._int_property(properties, "energy", 100),
                hunger=self._int_property(properties, "hunger", 0),
            )
            world.add_npc(created)

        return self._success(intervention, "object created", True), None, created

    def _remove(self, world, intervention):
        resolution = self.resolver.resolve(world, intervention.target)
        if resolution.namespace == "resource" and resolution.identifier == "Food":
            raise ValueError("the legacy Food resource cannot be removed")
        collection = resolution.collection
        before = resolution.value
        if isinstance(collection, dict):
            del collection[resolution.key]
        else:
            collection.remove(resolution.key)
        return self._success(intervention, "object removed", True), before, None

    def _move(self, world, intervention):
        resolution = self.resolver.resolve(world, intervention.target)
        if resolution.namespace != "npc":
            raise ValueError("MOVE currently requires an NPC target")
        location = intervention.properties.get("location", intervention.value)
        if not isinstance(location, str) or not location.strip():
            raise ValueError("MOVE requires a non-empty location")
        npc = resolution.value
        before = npc.location
        npc.move_to(location)
        return self._success(
            intervention,
            "object moved",
            before != npc.location,
        ), before, npc.location

    def _trigger_event(self, world, intervention):
        namespace, identifier = self.resolver.parse(intervention.target)
        if namespace != "event":
            raise ValueError("TRIGGER_EVENT requires an event target")
        properties = dict(intervention.properties)
        event_type = properties.pop("event_type", identifier.upper())
        actor = properties.pop("actor", "World")
        target = properties.pop("target", None)
        description = properties.pop(
            "description",
            f"Event triggered: {identifier}.",
        )
        if properties:
            raise ValueError(
                f"Unsupported event properties: {sorted(properties)}"
            )
        event = WorldEvent(
            day=world.clock.day,
            hour=world.clock.hour,
            event_type=event_type,
            actor=actor,
            target=target,
            description=description,
        )
        world.event_log.add(event)
        return self._success(intervention, "event triggered", True), None, event

    def _change_environment(self, world, intervention):
        resolution = self.resolver.resolve(world, intervention.target)
        value = intervention.value
        if "value" in intervention.properties:
            if value is not None:
                raise ValueError("environment value specified twice")
            value = intervention.properties["value"]
        if resolution.identifier == "drought":
            if not isinstance(value, bool):
                raise TypeError("drought value must be boolean")
            before = world.environment_system.drought_active
            if value:
                world.environment_system.start_drought(world)
            else:
                world.environment_system.end_drought(world)
            after = world.environment_system.drought_active
        elif resolution.identifier == "random_events_enabled":
            if not isinstance(value, bool):
                raise TypeError("random_events_enabled value must be boolean")
            before = world.environment_system.random_events_enabled
            world.environment_system.random_events_enabled = value
            after = value
        elif resolution.identifier == "climate":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("climate value must be a non-empty string")
            before = world.metadata.get("climate")
            world.metadata["climate"] = value
            after = value
        else:
            raise ValueError("unsupported environment target")
        return self._success(
            intervention,
            "environment changed",
            before != after,
        ), before, after

    def _change_rule(self, world, intervention):
        resolution = self.resolver.resolve(world, intervention.target)
        if resolution.namespace not in {"rule", "world"}:
            raise ValueError("CHANGE_RULE requires a rule target")
        if callable(intervention.value):
            raise ValueError("rules cannot contain executable values")
        if intervention.value is None and "value" not in intervention.properties:
            raise ValueError("CHANGE_RULE requires a value")
        value = intervention.properties.get("value", intervention.value)
        if callable(value):
            raise ValueError("rules cannot contain executable values")
        before = world.rules.get(resolution.key)
        world.rules[resolution.key] = value
        after = value
        return self._success(
            intervention,
            "rule changed",
            before != after,
        ), before, after

    def _advance_time(self, world, intervention):
        steps = intervention.value
        before = (world.clock.day, world.clock.hour)
        for _ in range(steps):
            world.clock.tick()
        after = (world.clock.day, world.clock.hour)
        return self._success(
            intervention,
            "time advanced",
            before != after,
        ), before, after

    def _validate_updates(
        self,
        world,
        resolution: TargetResolution,
        updates: dict[str, Any],
    ) -> None:
        allowed = {
            "resource": {"quantity", "name"},
            "npc": {
                "name",
                "role",
                "money",
                "home",
                "location",
                "food",
                "energy",
                "hunger",
                "reputation",
            },
            "building": {"name", "building_type", "money"},
            "entity": {
                "name",
                "entity_type",
                "location",
                "properties",
            },
            "faction": {"name", "faction_type"},
            "world": {"value"},
            "rule": {"value"},
            "environment": {"value"},
        }
        unsupported = set(updates) - allowed.get(resolution.namespace, set())
        if unsupported:
            raise ValueError(
                f"Unsupported update properties: {sorted(unsupported)}"
            )
        for key, value in updates.items():
            if key in {"name", "role", "home", "location", "building_type", "entity_type", "faction_type"}:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{key} must be a non-empty string")
            if key in {"money", "food", "energy", "hunger", "reputation", "quantity"}:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise TypeError(f"{key} must be an integer")
            if resolution.namespace == "resource" and key == "quantity" and value < 0:
                raise ValueError("resource quantity cannot be negative")
            if resolution.namespace == "npc":
                self._validate_npc_value(key, value)
            if resolution.namespace == "building" and key == "money" and value < 0:
                raise ValueError("building money cannot be negative")
            if resolution.namespace == "entity" and key == "properties":
                if not isinstance(value, Mapping):
                    raise TypeError("entity properties must be a mapping")
            if resolution.namespace == "world" and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError("world metadata must be a non-empty string")
            if resolution.namespace == "rule" and callable(value):
                raise ValueError("rules cannot contain executable values")

    def _apply_updates(
        self,
        world,
        resolution: TargetResolution,
        updates: dict[str, Any],
    ) -> None:
        if resolution.namespace == "world":
            key = resolution.key
            if key not in {"era", "geography", "climate"}:
                raise ValueError("unsupported world update")
            world.metadata[key] = updates.get("value")
            return
        if resolution.namespace == "rule":
            world.rules[resolution.key] = updates["value"]
            return
        if resolution.namespace == "environment":
            self._change_environment(
                world,
                GodIntervention(
                    operation=InterventionOperation.CHANGE_ENVIRONMENT,
                    target=f"environment:{resolution.identifier}",
                    value=updates["value"],
                ),
            )
            return
        target = resolution.value
        if resolution.namespace == "entity" and "properties" in updates:
            target.properties = dict(updates.pop("properties"))
        if resolution.namespace == "resource" and "quantity" in updates:
            amount = updates["quantity"] - target.quantity
            if amount > 0:
                target.add(amount)
            elif amount < 0 and not target.consume(-amount):
                raise ValueError("resource quantity is insufficient")
            updates = {key: value for key, value in updates.items() if key != "quantity"}
        for key, value in updates.items():
            if key == "location":
                if resolution.namespace == "entity":
                    target.location = value
                else:
                    target.move_to(value)
            else:
                setattr(target, key, value)

    @staticmethod
    def _validate_npc_value(key: str, value: Any) -> None:
        if key in {"energy", "hunger"} and not 0 <= value <= 100:
            raise ValueError(f"{key} must be between 0 and 100")
        if key == "reputation" and not -100 <= value <= 100:
            raise ValueError("reputation must be between -100 and 100")
        if key in {"money", "food"} and value < 0:
            raise ValueError(f"{key} cannot be negative")

    @staticmethod
    def _snapshot(resolution: TargetResolution):
        value = resolution.value
        if resolution.namespace in {"world", "rule", "environment"}:
            return resolution.value
        if isinstance(value, Resource):
            return (value.name, value.quantity)
        if isinstance(value, NPC):
            return (
                value.name,
                value.role,
                value.money,
                value.home,
                value.location,
                value.food,
                value.energy,
                value.hunger,
                value.reputation,
            )
        if isinstance(value, Building):
            return (value.name, value.building_type, value.money)
        if isinstance(value, WorldEntity):
            return (
                value.name,
                value.entity_type,
                value.location,
                dict(value.properties),
            )
        if isinstance(value, Faction):
            return (value.name, value.faction_type)
        return value

    @staticmethod
    def _int_property(properties, key: str, default: int) -> int:
        value = properties.pop(key, default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{key} must be an integer")
        return value

    @staticmethod
    def _str_property(properties, key: str, default: str) -> str:
        value = properties.pop(key, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value

    @staticmethod
    def _success(intervention, message: str, changed: bool):
        return InterventionResult(
            success=True,
            operation=intervention.operation,
            target=intervention.target,
            message=message,
            changed=changed,
        )

    @staticmethod
    def _failure(intervention, message: str):
        return InterventionResult(
            success=False,
            operation=intervention.operation,
            target=intervention.target,
            message=message,
            changed=False,
        )

    @staticmethod
    def _record(world, intervention, result, before, after) -> None:
        world.intervention_history.append(
            InterventionAudit(
                intervention=intervention,
                result=result,
                day=world.clock.day,
                hour=world.clock.hour,
                before=before,
                after=after,
            )
        )
