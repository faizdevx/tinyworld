from collections.abc import Mapping
from typing import Any

from WORLD.AI.action import ActionType
from WORLD.Buildings.buildings import Building
from WORLD.Entities.entity import WorldEntity
from WORLD.Events.event import (
    Consequence,
    EventProcessingResult,
    EventProposal,
    EventResolution,
    EventSource,
    EventValidationResult,
    WorldEvent,
)
from WORLD.Factions.faction import Faction
from WORLD.Interventions.resolver import TargetResolver
from WORLD.NPCs.memory import Memory
from WORLD.NPCs.npc import NPC
from WORLD.Resources.food import Resource


class EventValidator:
    """Validate attempted events against authoritative World state."""

    def __init__(self, target_resolver: TargetResolver | None = None) -> None:
        self.target_resolver = target_resolver or TargetResolver()

    def validate(self, world, proposal: EventProposal) -> EventValidationResult:
        try:
            if proposal.source == EventSource.NPC:
                return self._validate_npc(world, proposal)
            if proposal.source == EventSource.GOD:
                return self._validate_god(world, proposal)
            return self._validate_system(world, proposal)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            return EventValidationResult(False, str(exc))

    def _validate_npc(self, world, proposal: EventProposal):
        if not proposal.actor.startswith("npc:"):
            return EventValidationResult(False, "NPC actor must use npc:<name>")
        actor_name = proposal.actor.removeprefix("npc:")
        npc = self._find_named(world.npcs, actor_name)
        if npc is None:
            return EventValidationResult(False, "NPC actor does not exist")

        action = proposal.action_type
        if action in {ActionType.SHOP, ActionType.OBTAIN_FOOD}:
            quantity = proposal.properties.get("quantity", 1)
            if not self._positive_integer(quantity):
                return EventValidationResult(False, "purchase quantity must be positive")
            if proposal.target not in {None, "resource:Food"}:
                return EventValidationResult(False, "shop only sells the requested Food resource")
            if npc.location != world.shop.name:
                return EventValidationResult(False, "NPC is not at the shop")
            total = world.shop.food_price * quantity
            if world.shop.food < quantity:
                return EventValidationResult(False, "shop has insufficient Food")
            if npc.money < total:
                return EventValidationResult(False, "NPC cannot afford the purchase")
            return EventValidationResult(
                True,
                "purchase is valid",
                {
                    "npc_name": npc.name,
                    "quantity": quantity,
                    "unit_price": world.shop.food_price,
                    "total_price": total,
                    "shop_name": world.shop.name,
                },
            )

        if action == ActionType.EAT:
            if npc.food <= 0:
                return EventValidationResult(False, "NPC has no Food to eat")
            return EventValidationResult(True, "eating is valid", {"npc_name": npc.name})

        if action == ActionType.SLEEP:
            if npc.energy >= 100:
                return EventValidationResult(False, "NPC has no need to sleep")
            return EventValidationResult(True, "sleep is valid", {"npc_name": npc.name})

        if action == ActionType.WORK:
            if npc.location not in {"Village Farm", "General Store"}:
                return EventValidationResult(False, "NPC is not at a workplace")
            if npc.energy <= 0:
                return EventValidationResult(False, "NPC has no energy to work")
            return EventValidationResult(True, "work is valid", {"npc_name": npc.name})

        if action == ActionType.SOCIALIZE:
            target = proposal.target
            if not target or not target.startswith("npc:"):
                return EventValidationResult(False, "social interaction requires an npc target")
            other_name = target.removeprefix("npc:")
            other = self._find_named(world.npcs, other_name)
            if other is None or other is npc:
                return EventValidationResult(False, "social target does not exist")
            if other.location != npc.location:
                return EventValidationResult(False, "NPCs are not at the same location")
            return EventValidationResult(
                True,
                "social interaction is valid",
                {"npc_name": npc.name, "other_name": other.name},
            )

        return EventValidationResult(False, f"unsupported NPC action: {action}")

    def _validate_god(self, world, proposal: EventProposal):
        operation = str(proposal.action_type).lower()
        target = proposal.target
        if not target:
            return EventValidationResult(False, "God operation requires a target")

        if operation in {"spawn", "create"}:
            namespace, name = self.target_resolver.parse(target)
            if namespace not in {"entity", "faction", "building", "npc", "resource"}:
                return EventValidationResult(False, "unsupported object namespace")
            if self._target_exists(world, namespace, name):
                return EventValidationResult(False, "target already exists")
            properties = dict(proposal.properties)
            try:
                self._construct(namespace, name, properties, attach=False)
            except (TypeError, ValueError, KeyError) as exc:
                return EventValidationResult(False, str(exc))
            return EventValidationResult(
                True,
                "creation is valid",
                {"namespace": namespace, "name": name, "properties": properties},
            )

        if operation in {"despawn", "remove"}:
            resolution = self.target_resolver.resolve(world, target)
            if resolution.namespace == "resource" and resolution.identifier == "Food":
                return EventValidationResult(False, "legacy Food resource cannot be removed")
            return EventValidationResult(
                True,
                "removal is valid",
                {"namespace": resolution.namespace, "name": resolution.identifier},
            )

        if operation == "change_resource":
            resolution = self.target_resolver.resolve(world, target)
            if resolution.namespace != "resource":
                return EventValidationResult(False, "resource change requires a resource target")
            amount = proposal.properties.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool):
                return EventValidationResult(False, "resource amount must be an integer")
            resource = resolution.value
            if amount < 0 and resource.quantity < -amount:
                return EventValidationResult(False, "resource quantity is insufficient")
            return EventValidationResult(
                True,
                "resource change is valid",
                {
                    "resource_name": resource.name,
                    "amount": amount,
                    "before": resource.quantity,
                },
            )

        if operation == "move":
            resolution = self.target_resolver.resolve(world, target)
            location = proposal.properties.get("location")
            if not isinstance(location, str) or not location.strip():
                return EventValidationResult(False, "destination must be a non-empty location")
            if resolution.namespace not in {"npc", "entity"}:
                return EventValidationResult(False, "target cannot be moved")
            return EventValidationResult(
                True,
                "move is valid",
                {
                    "namespace": resolution.namespace,
                    "name": resolution.identifier,
                    "before": getattr(resolution.value, "location", None),
                    "location": location,
                },
            )

        if operation == "trigger_event":
            namespace, name = self.target_resolver.parse(target)
            if namespace != "event":
                return EventValidationResult(False, "event trigger requires an event target")
            return EventValidationResult(True, "event trigger is valid", {"event_name": name})

        return EventValidationResult(False, f"unsupported God operation: {operation}")

    def _validate_system(self, world, proposal: EventProposal):
        if proposal.action_type == "harvest":
            quantity = proposal.properties.get("quantity")
            if not self._positive_integer(quantity):
                return EventValidationResult(
                    False,
                    "harvest quantity must be positive",
                )
            try:
                self.target_resolver.resolve(world, "resource:Food")
            except (ValueError, KeyError) as exc:
                return EventValidationResult(False, str(exc))
            return EventValidationResult(
                True,
                "harvest is valid",
                {"quantity": quantity},
            )

        if proposal.action_type == "restock":
            quantity = proposal.properties.get("quantity")
            if not self._positive_integer(quantity):
                return EventValidationResult(
                    False,
                    "restock quantity must be positive",
                )
            try:
                food = self.target_resolver.resolve(
                    world,
                    "resource:Food",
                ).value
            except (ValueError, KeyError) as exc:
                return EventValidationResult(False, str(exc))
            if food.quantity < quantity:
                return EventValidationResult(
                    False,
                    "village has insufficient Food to restock",
                )
            return EventValidationResult(
                True,
                "restock is valid",
                {"quantity": quantity},
            )

        if proposal.action_type == "food_gift":
            donor_name = proposal.properties.get("donor")
            receiver_name = proposal.properties.get("receiver")
            donor = self._find_named(world.npcs, donor_name)
            receiver = self._find_named(world.npcs, receiver_name)
            if donor is None or receiver is None or donor is receiver:
                return EventValidationResult(
                    False,
                    "gift participants must exist and differ",
                )
            system = world.cooperation_system
            if not system._needs_help(receiver, world):
                return EventValidationResult(
                    False,
                    "receiver does not need food help",
                )
            if not system._can_donate(donor, receiver):
                return EventValidationResult(
                    False,
                    "donor cannot give food to receiver",
                )
            return EventValidationResult(
                True,
                "food gift is valid",
                {
                    "donor": donor.name,
                    "receiver": receiver.name,
                    "quantity": system.FOOD_TRANSFER_AMOUNT,
                },
            )

        if proposal.action_type == "conflict":
            first_name = proposal.properties.get("first")
            second_name = proposal.properties.get("second")
            first = self._find_named(world.npcs, first_name)
            second = self._find_named(world.npcs, second_name)
            if first is None or second is None or first is second:
                return EventValidationResult(
                    False,
                    "conflict participants must exist and differ",
                )
            system = world.conflict_system
            if world.shop.food > system.FOOD_SCARCITY_THRESHOLD:
                return EventValidationResult(
                    False,
                    "food is not scarce enough for conflict",
                )
            if not system._needs_food(first, world) or not system._needs_food(second, world):
                return EventValidationResult(
                    False,
                    "both participants must need food",
                )
            if first.location != second.location:
                return EventValidationResult(
                    False,
                    "conflict participants are not co-located",
                )
            return EventValidationResult(
                True,
                "conflict is valid",
                {"first": first.name, "second": second.name},
            )

        if proposal.action_type != "system_event":
            return EventValidationResult(
                False,
                "system proposals currently support system_event only",
            )
        if not proposal.target or not proposal.target.startswith("event:"):
            return EventValidationResult(
                False,
                "system event requires an event:<name> target",
            )
        event_name = proposal.target.removeprefix("event:").strip()
        if not event_name:
            return EventValidationResult(False, "event name cannot be empty")
        return EventValidationResult(
            True,
            "system event is valid",
            {"event_name": event_name},
        )

    def _target_exists(self, world, namespace: str, name: str) -> bool:
        if namespace == "resource":
            return name in world.resources
        collection_name = self.target_resolver.COLLECTION_NAMESPACES.get(namespace)
        if collection_name is None:
            return False
        return self._find_named(getattr(world, collection_name), name) is not None

    @staticmethod
    def _find_named(collection, name: str):
        return next((item for item in collection if item.name == name), None)

    @staticmethod
    def _positive_integer(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _construct(namespace: str, name: str, properties: dict[str, Any], *, attach: bool):
        if namespace == "entity":
            extra = dict(properties)
            entity_type = extra.pop("entity_type", "generic")
            location = extra.pop("location", None)
            nested = extra.pop("properties", {})
            if not isinstance(nested, Mapping):
                raise TypeError("entity properties must be a mapping")
            if not isinstance(nested, dict):
                nested = dict(nested)
            if "size" in extra:
                nested = {**nested, "size": extra.pop("size")}
            if extra:
                raise ValueError(f"unsupported entity properties: {sorted(extra)}")
            return WorldEntity(name, entity_type, location, nested)
        if namespace == "faction":
            extra = dict(properties)
            faction_type = extra.pop("faction_type", "generic")
            if extra:
                raise ValueError(f"unsupported faction properties: {sorted(extra)}")
            return Faction(name, faction_type)
        if namespace == "building":
            extra = dict(properties)
            building_type = extra.pop("building_type", "generic")
            money = extra.pop("money", 0)
            if extra:
                raise ValueError(f"unsupported building properties: {sorted(extra)}")
            return Building(name, building_type, money)
        if namespace == "resource":
            extra = dict(properties)
            quantity = extra.pop("quantity", 0)
            if extra:
                raise ValueError(f"unsupported resource properties: {sorted(extra)}")
            return Resource(name, quantity)
        if namespace == "npc":
            extra = dict(properties)
            role = extra.pop("role", "villager")
            money = extra.pop("money", 0)
            home = extra.pop("home", "Settlement")
            location = extra.pop("location", "Settlement")
            food = extra.pop("food", 0)
            energy = extra.pop("energy", 100)
            hunger = extra.pop("hunger", 0)
            if extra:
                raise ValueError(f"unsupported NPC properties: {sorted(extra)}")
            return NPC(name, role, money, home, location, food, energy, hunger)
        raise ValueError(f"unsupported object namespace: {namespace}")


class EventResolver:
    """Turn a valid proposal into a structured record of world reality."""

    def resolve(
        self,
        world,
        proposal: EventProposal,
        validation: EventValidationResult,
    ) -> EventResolution:
        if not validation.success:
            raise ValueError("cannot resolve an invalid proposal")

        details = dict(validation.details)
        action = proposal.action_type
        if proposal.source == EventSource.NPC:
            actor_name = proposal.actor.removeprefix("npc:")
            if action in {ActionType.SHOP, ActionType.OBTAIN_FOOD}:
                quantity = details["quantity"]
                total = details["total_price"]
                consequences = (
                    Consequence(
                        "PURCHASE",
                        actor_name,
                        {
                            "quantity": quantity,
                            "unit_price": details["unit_price"],
                            "total_price": total,
                            "shop_name": details["shop_name"],
                        },
                    ),
                )
                description = f"{actor_name} bought {quantity} Food for {total}."
                target = details["shop_name"]
                event_type = "PURCHASE"
                properties = {
                    "item": "Food",
                    "quantity": quantity,
                    "unit_price": details["unit_price"],
                    "price": total,
                }
            else:
                event_type = {
                    ActionType.EAT: "EAT",
                    ActionType.SLEEP: "SLEEP",
                    ActionType.WORK: "WORK",
                    ActionType.SOCIALIZE: "SOCIALIZE",
                }[action]
                target = proposal.target.removeprefix("npc:") if proposal.target else None
                consequence_kind = (
                    "SOCIAL_INTERACTION"
                    if action == ActionType.SOCIALIZE
                    else event_type
                )
                consequences = (
                    Consequence(
                        consequence_kind,
                        actor_name,
                        details,
                    ),
                )
                description = f"{actor_name} performed {event_type.lower()}."
                properties = dict(details)
        elif proposal.source == EventSource.GOD:
            operation = str(action).lower()
            namespace, identifier = TargetResolver.parse(proposal.target)
            event_type = {
                "create": "SPAWN",
                "spawn": "SPAWN",
                "remove": "DESPAWN",
                "despawn": "DESPAWN",
                "change_resource": "RESOURCE_CHANGE",
                "move": "MOVE",
                "trigger_event": "SYSTEM_EVENT",
            }[operation]
            target = identifier
            consequence_properties = dict(proposal.properties)
            consequence_properties.update(details)
            consequence_kind = (
                "SYSTEM_EVENT"
                if operation == "trigger_event"
                else operation.upper()
            )
            consequences = (
                Consequence(consequence_kind, proposal.target, consequence_properties),
            )
            properties = {
                "namespace": namespace,
                **dict(proposal.properties),
            }
            if operation in {"create", "spawn"}:
                description = f"{identifier} entered the world."
            elif operation in {"remove", "despawn"}:
                description = f"{identifier} left the active world."
            elif operation == "change_resource":
                description = f"{identifier} quantity changed by {proposal.properties['amount']}."
            elif operation == "move":
                description = f"{identifier} moved to {proposal.properties['location']}."
            else:
                description = str(proposal.properties.get("description", f"{identifier} occurred."))
                if operation == "trigger_event":
                    event_type = str(
                        proposal.properties.get("event_type", identifier.upper())
                    )
                    target = proposal.properties.get("target")
                    properties = dict(proposal.properties)
        else:
            system_action = proposal.action_type
            if system_action == "harvest":
                quantity = details["quantity"]
                event_type = "HARVEST"
                target = None
                description = f"Farmers produced {quantity} food."
                properties = {"quantity": quantity, "resource": "Food"}
                consequences = (
                    Consequence("HARVEST", "Food", {"quantity": quantity}),
                )
            elif system_action == "restock":
                quantity = details["quantity"]
                event_type = "RESTOCK"
                target = world.shop.name
                description = f"{world.shop.name} received {quantity} food."
                properties = {"quantity": quantity, "resource": "Food"}
                consequences = (
                    Consequence(
                        "RESTOCK",
                        "Food",
                        {"quantity": quantity, "shop_name": world.shop.name},
                    ),
                )
            elif system_action == "food_gift":
                donor = details["donor"]
                receiver = details["receiver"]
                quantity = details["quantity"]
                event_type = "FOOD_GIFT"
                target = receiver
                description = f"{donor} gave food to {receiver}."
                properties = {"quantity": quantity}
                consequences = (
                    Consequence("FOOD_GIFT", donor, details),
                )
            elif system_action == "conflict":
                first = details["first"]
                second = details["second"]
                event_type = "CONFLICT"
                target = second
                description = f"{first} argued with {second} over scarce food."
                properties = {"participants": (first, second)}
                consequences = (
                    Consequence("CONFLICT", first, details),
                )
            else:
                event_name = details["event_name"]
                event_type = str(
                    proposal.properties.get("event_type", event_name.upper())
                )
                target = proposal.properties.get("target")
                description = str(
                    proposal.properties.get(
                        "description",
                        f"{event_name} occurred.",
                    )
                )
                properties = dict(proposal.properties)
                consequences = (
                    Consequence("SYSTEM_EVENT", proposal.target, properties),
                )

        timestamp = proposal.timestamp or (world.clock.day, world.clock.hour)
        event = WorldEvent(
            day=timestamp[0],
            hour=timestamp[1],
            event_type=event_type,
            actor=(
                proposal.actor.removeprefix("npc:")
                if proposal.source == EventSource.NPC
                else details.get(
                    "donor",
                    details.get(
                        "first",
                        "Village"
                        if action in {"harvest", "restock"}
                        else proposal.actor,
                    ),
                )
                if proposal.source == EventSource.SYSTEM
                else proposal.actor
            ),
            target=target,
            description=description,
            properties=properties,
            consequences=consequences,
            sequence=len(world.event_log.events) + 1,
            cause=str(action.value) if isinstance(action, ActionType) else str(action),
        )
        return EventResolution(event=event, consequences=consequences)


class ConsequenceEngine:
    """Apply validated event consequences to authoritative World state."""

    def apply(self, world, proposal: EventProposal, resolution: EventResolution):
        if len(resolution.consequences) != 1:
            raise ValueError("exactly one consequence is supported per event")
        consequence = resolution.consequences[0]
        before = self._capture_before(world, proposal, consequence)
        kind = consequence.kind
        props = dict(consequence.properties)

        if kind == "PURCHASE":
            npc = self._find_named(world.npcs, consequence.target)
            shop = world.shop
            quantity = props["quantity"]
            total = props["total_price"]
            npc.money -= total
            shop.money += total
            shop.food -= quantity
            npc.food += quantity
        elif kind == "EAT":
            npc = self._find_named(world.npcs, consequence.target)
            if not npc.eat():
                raise ValueError("validated eating consequence failed")
        elif kind == "SLEEP":
            npc = self._find_named(world.npcs, consequence.target)
            was_at_work = npc.location in {"Village Farm", "General Store"}
            was_low_energy = npc.energy <= 30
            if npc.location != npc.home:
                npc.move_to(npc.home)
            old_energy = npc.energy
            npc.restore_energy(15)
            if was_at_work and was_low_energy and npc.energy > old_energy:
                world.work_status[npc.name] = "too_tired"
        elif kind == "WORK":
            npc = self._find_named(world.npcs, consequence.target)
            npc.use_energy(5)
            world.work_status[npc.name] = "worked"
        elif kind == "SOCIAL_INTERACTION":
            first = self._find_named(world.npcs, consequence.target)
            second = self._find_named(world.npcs, str(props["other_name"]))
            first.change_relationship(second, 1)
            second.change_relationship(first, 1)
            first.remember(Memory(world.clock.day, world.clock.hour, f"Spent time with {second.name}", 1))
            second.remember(Memory(world.clock.day, world.clock.hour, f"Spent time with {first.name}", 1))
        elif kind == "HARVEST":
            world.resources[consequence.target].add(props["quantity"])
        elif kind == "RESTOCK":
            resource = world.resources[consequence.target]
            quantity = props["quantity"]
            if not resource.consume(quantity):
                raise ValueError("validated restock consequence failed")
            world.shop.food += quantity
        elif kind == "FOOD_GIFT":
            donor = self._find_named(world.npcs, consequence.target)
            receiver = self._find_named(world.npcs, props["receiver"])
            quantity = props["quantity"]
            if not donor.consume_food(quantity):
                raise ValueError("validated gift consequence failed")
            receiver.add_food(quantity)
            donor.change_relationship(receiver, 1)
            receiver.change_relationship(donor, 1)
            donor.remember(
                Memory(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event=f"Gave food to {receiver.name}",
                    importance=2,
                )
            )
            receiver.remember(
                Memory(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event=f"Received food from {donor.name}",
                    importance=2,
                )
            )
            donor.reputation = min(donor.reputation + 5, 100)
        elif kind == "CONFLICT":
            first = self._find_named(world.npcs, consequence.target)
            second = self._find_named(world.npcs, props["second"])
            change = world.conflict_system.RELATIONSHIP_CHANGE
            first.change_relationship(second, change)
            second.change_relationship(first, change)
            first.remember(
                Memory(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event=f"Argued with {second.name}",
                    importance=2,
                )
            )
            second.remember(
                Memory(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event=f"Argued with {first.name}",
                    importance=2,
                )
            )
            world.reputation_system.apply_conflict(first)
            world.reputation_system.apply_conflict(second)
        elif kind in {"CREATE", "SPAWN"}:
            namespace = props["namespace"]
            name = props["name"]
            created = EventValidator._construct(
                namespace,
                name,
                dict(props["properties"]),
                attach=False,
            )
            if namespace == "entity":
                world.add_entity(created)
            elif namespace == "building":
                world.add_building(created)
            elif namespace == "faction":
                world.add_faction(created)
            elif namespace == "npc":
                world.add_npc(created)
            elif namespace == "resource":
                world.resources[name] = created
        elif kind in {"REMOVE", "DESPAWN"}:
            namespace = props["namespace"]
            name = props["name"]
            if namespace == "resource":
                del world.resources[name]
            else:
                collection = getattr(world, TargetResolver.COLLECTION_NAMESPACES[namespace])
                collection.remove(self._find_named(collection, name))
        elif kind == "CHANGE_RESOURCE":
            resource = world.resources[props["resource_name"]]
            amount = props["amount"]
            if amount > 0:
                resource.add(amount)
            elif amount < 0 and not resource.consume(-amount):
                raise ValueError("validated resource consequence failed")
        elif kind == "MOVE":
            namespace = props["namespace"]
            collection = getattr(world, TargetResolver.COLLECTION_NAMESPACES[namespace])
            target = self._find_named(collection, props["name"])
            if namespace == "npc":
                target.move_to(props["location"])
            else:
                target.location = props["location"]
        elif kind == "SYSTEM_EVENT":
            pass
        else:
            raise ValueError(f"Unsupported consequence kind: {kind}")

        after = self._capture_after(world, proposal, consequence)
        return before, after

    def _capture_before(self, world, proposal, consequence):
        if consequence.kind == "PURCHASE":
            npc = self._find_named(world.npcs, consequence.target)
            return (npc.money, npc.food, world.shop.money, world.shop.food)
        if consequence.kind == "CHANGE_RESOURCE":
            name = consequence.properties["resource_name"]
            return world.resources[name].quantity
        if consequence.kind in {"CREATE", "SPAWN", "REMOVE", "DESPAWN"}:
            return None
        if consequence.kind == "MOVE":
            return consequence.properties["before"]
        return None

    def _capture_after(self, world, proposal, consequence):
        if consequence.kind == "PURCHASE":
            npc = self._find_named(world.npcs, consequence.target)
            return (npc.money, npc.food, world.shop.money, world.shop.food)
        if consequence.kind == "CHANGE_RESOURCE":
            name = consequence.properties["resource_name"]
            return world.resources[name].quantity
        if consequence.kind in {"CREATE", "SPAWN"}:
            return consequence.properties["name"]
        if consequence.kind in {"REMOVE", "DESPAWN"}:
            return None
        if consequence.kind == "MOVE":
            return consequence.properties["location"]
        return None

    @staticmethod
    def _find_named(collection, name: str):
        return next(item for item in collection if item.name == name)


class EventEngine:
    def __init__(
        self,
        validator: EventValidator | None = None,
        resolver: EventResolver | None = None,
        consequence_engine: ConsequenceEngine | None = None,
    ) -> None:
        self.validator = validator or EventValidator()
        self.resolver = resolver or EventResolver()
        self.consequence_engine = consequence_engine or ConsequenceEngine()

    def process(self, world, proposal: EventProposal) -> EventProcessingResult:
        if not isinstance(proposal, EventProposal):
            raise TypeError("proposal must be an EventProposal")
        validation = self.validator.validate(world, proposal)
        if not validation.success:
            return EventProcessingResult(
                success=False,
                validation=validation,
                reason=validation.reason,
            )
        try:
            resolution = self.resolver.resolve(world, proposal, validation)
            before, after = self.consequence_engine.apply(
                world,
                proposal,
                resolution,
            )
        except (TypeError, ValueError, KeyError, StopIteration) as exc:
            failed = EventValidationResult(False, str(exc))
            return EventProcessingResult(False, failed, reason=str(exc))
        world.event_log.add(resolution.event)
        return EventProcessingResult(
            success=True,
            validation=validation,
            resolution=resolution,
            reason="event applied",
            before=before,
            after=after,
        )

    def process_npc_action(
        self,
        world,
        npc,
        action: ActionType,
        target=None,
        *,
        quantity: int = 1,
    ) -> EventProcessingResult:
        target_name = None
        if action == ActionType.SOCIALIZE and target is not None:
            target_name = f"npc:{target.name}"
        elif action == ActionType.SOCIALIZE:
            other = next(
                (
                    candidate
                    for candidate in world.npcs
                    if candidate is not npc
                    and candidate.location == npc.location
                ),
                None,
            )
            if other is not None:
                target_name = f"npc:{other.name}"
        elif action in {ActionType.SHOP, ActionType.OBTAIN_FOOD}:
            target_name = "resource:Food"
        proposal = EventProposal(
            actor=f"npc:{npc.name}",
            action_type=action,
            target=target_name,
            properties={"quantity": quantity} if action == ActionType.SHOP else {},
            source=EventSource.NPC,
            timestamp=(world.clock.day, world.clock.hour),
        )
        return self.process(world, proposal)
