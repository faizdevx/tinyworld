"""Deterministic application of effects to world state.

Reducers enforce structural validity only: referenced things exist, quantities
stay non-negative, ids are unique. Whether an action is plausible is the Game
Master's decision and is made before effects reach this module.
"""

import re
from collections.abc import Iterable
from datetime import timedelta

from tinyworld.core import effects as fx
from tinyworld.core.events import Event
from tinyworld.core.ids import edge_key, relation_key
from tinyworld.core.registry import REGISTRY, AttrRegistry
from tinyworld.core.state import Entity, Relation, WorldState

_RULE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_HOLDABLE = ("item", "resource")


class EffectError(ValueError):
    """An effect cannot be applied to the current state."""


def _entity(state: WorldState, entity_id: str) -> Entity:
    entity = state.entities.get(entity_id)
    if entity is None:
        raise EffectError(f"unknown entity: {entity_id}")
    return entity


def _place(state: WorldState, entity_id: str) -> Entity:
    place = _entity(state, entity_id)
    if place.kind != "place":
        raise EffectError(f"{entity_id} is not a place")
    return place


def _holdable(state: WorldState, entity_id: str) -> Entity:
    item = _entity(state, entity_id)
    if item.kind not in _HOLDABLE:
        raise EffectError(f"{entity_id} cannot be held in an inventory")
    return item


def _change_inventory(holder: Entity, item: str, delta: int) -> None:
    quantity = holder.inventory.get(item, 0) + delta
    if quantity < 0:
        raise EffectError(f"{holder.id} does not have enough {item}")
    if quantity == 0:
        holder.inventory.pop(item, None)
    else:
        holder.inventory[item] = quantity


def _check_attrs(registry: AttrRegistry, kind: str, attrs: dict) -> None:
    for key, value in attrs.items():
        reason = registry.check(kind, key, value)
        if reason:
            raise EffectError(reason)


def apply_effect(
    state: WorldState,
    effect,
    registry: AttrRegistry = REGISTRY,
) -> None:
    """Apply one effect in place. Raises EffectError when it does not fit."""
    if isinstance(effect, fx.MoveEntity):
        entity = _entity(state, effect.entity)
        if entity.kind == "place":
            raise EffectError("places cannot be moved")
        _place(state, effect.to)
        entity.location = effect.to
        if state.grid and entity.kind == "person":
            _arrive(state, entity, effect.to)

    elif isinstance(effect, fx.TransferItem):
        _holdable(state, effect.item)
        source = _entity(state, effect.source)
        dest = _entity(state, effect.dest)
        if source.id == dest.id:
            raise EffectError("transfer source and destination are the same")
        _change_inventory(source, effect.item, -effect.quantity)
        _change_inventory(dest, effect.item, effect.quantity)

    elif isinstance(effect, fx.ChangeQuantity):
        _holdable(state, effect.item)
        _change_inventory(_entity(state, effect.holder), effect.item, effect.delta)

    elif isinstance(effect, fx.SetAttr):
        entity = _entity(state, effect.entity)
        _check_attrs(registry, entity.kind, {effect.key: effect.value})
        if effect.value is None:
            entity.attrs.pop(effect.key, None)
        else:
            entity.attrs[effect.key] = effect.value

    elif isinstance(effect, fx.CreateEntity):
        entity = effect.entity
        if entity.id in state.entities:
            raise EffectError(f"entity already exists: {entity.id}")
        if entity.location is not None:
            _place(state, entity.location)
        _check_attrs(registry, entity.kind, entity.attrs)
        for item, quantity in entity.inventory.items():
            _holdable(state, item)
            if quantity <= 0:
                raise EffectError("inventory quantities must be positive")
        state.entities[entity.id] = entity.model_copy(deep=True)

    elif isinstance(effect, fx.RemoveEntity):
        entity = _entity(state, effect.entity)
        if entity.kind == "place" and any(
            other.location == entity.id for other in state.entities.values()
        ):
            raise EffectError(f"{entity.id} is not empty")
        del state.entities[entity.id]
        marker = entity.id
        state.edges = {
            key: edge for key, edge in state.edges.items()
            if marker not in key.split("|")
        }
        state.relations = {
            key: relation for key, relation in state.relations.items()
            if marker not in key.split(">")
        }
        for other in state.entities.values():
            other.inventory.pop(marker, None)

    elif isinstance(effect, fx.Kill):
        entity = _entity(state, effect.entity)
        if entity.kind != "person":
            raise EffectError(f"{entity.id} is not a person")
        if not entity.alive:
            raise EffectError(f"{entity.id} is already dead")
        entity.alive = False

    elif isinstance(effect, fx.SetRelation):
        _entity(state, effect.source)
        _entity(state, effect.dest)
        if effect.source == effect.dest:
            raise EffectError("an entity cannot have a relation with itself")
        state.relations[relation_key(effect.source, effect.dest)] = Relation(
            kind=effect.kind, value=effect.value, note=effect.note
        )

    elif isinstance(effect, fx.SetEdge):
        _place(state, effect.a)
        _place(state, effect.b)
        if effect.a == effect.b:
            raise EffectError("a place cannot connect to itself")
        key = edge_key(effect.a, effect.b)
        if effect.edge is None:
            if key not in state.edges:
                raise EffectError(f"no edge between {effect.a} and {effect.b}")
            del state.edges[key]
        else:
            state.edges[key] = effect.edge.model_copy()

    elif isinstance(effect, fx.AssertFact):
        fact = effect.fact.model_copy(deep=True)
        if fact.valid_from is None:
            fact.valid_from = state.sim_time
        state.facts[fact.id] = fact

    elif isinstance(effect, fx.RetractFact):
        if not state.fact_holds(effect.fact_id):
            raise EffectError(f"fact does not hold: {effect.fact_id}")
        state.facts[effect.fact_id].valid_to = state.sim_time

    elif isinstance(effect, fx.StartProcess):
        process = effect.process
        if process.id in state.processes:
            raise EffectError(f"process already exists: {process.id}")
        if process.status != "active":
            raise EffectError("a new process must be active")
        _entity(state, process.owner)
        if process.location is not None:
            _place(state, process.location)
        state.processes[process.id] = process.model_copy(deep=True)

    elif isinstance(effect, fx.AdvanceProcess):
        process = state.processes.get(effect.process_id)
        if process is None or process.status != "active":
            raise EffectError(f"no active process: {effect.process_id}")
        process.progress = min(1.0, max(0.0, round(process.progress + effect.delta, 6)))

    elif isinstance(effect, fx.EndProcess):
        process = state.processes.get(effect.process_id)
        if process is None or process.status != "active":
            raise EffectError(f"no active process: {effect.process_id}")
        process.status = effect.status

    elif isinstance(effect, fx.MakeCommitment):
        commitment = effect.commitment
        if commitment.id in state.commitments:
            raise EffectError(f"commitment already exists: {commitment.id}")
        if commitment.status != "open":
            raise EffectError("a new commitment must be open")
        for who in (commitment.by, commitment.to):
            person = _entity(state, who)
            if person.kind != "person":
                raise EffectError(f"{who} is not a person")
        if commitment.by == commitment.to:
            raise EffectError("a person cannot promise themselves")
        if commitment.place is not None:
            _place(state, commitment.place)
        if commitment.item is not None:
            _holdable(state, commitment.item)
        if commitment.due <= state.sim_time:
            raise EffectError("a commitment must fall due in the future")
        state.commitments[commitment.id] = commitment.model_copy(deep=True)

    elif isinstance(effect, fx.ResolveCommitment):
        commitment = state.commitments.get(effect.commitment_id)
        if commitment is None or commitment.status != "open":
            raise EffectError(f"no open commitment: {effect.commitment_id}")
        commitment.status = effect.status

    elif isinstance(effect, fx.LearnKnowledge):
        from tinyworld.world import knowledge

        person = _entity(state, effect.person)
        if person.kind != "person" or not person.alive:
            raise EffectError(f"{effect.person} cannot learn anything")
        graph = knowledge.ideas(state)
        if effect.idea not in graph:
            raise EffectError(f"no such idea: {effect.idea}")
        if effect.by != "god":
            lacking = knowledge.missing(state, [person], effect.idea)
            if lacking:
                raise EffectError(
                    f"{person.name} lacks what {effect.idea} builds on: {', '.join(lacking)}"
                )
        mine = dict(knowledge.held(person))
        mine[effect.idea] = max(mine.get(effect.idea, 0), effect.level)
        person.attrs[knowledge.KEY] = mine

    elif isinstance(effect, fx.Utter):
        speaker = _entity(state, effect.speaker)
        if speaker.kind != "person" or not speaker.alive:
            raise EffectError(f"{effect.speaker} cannot speak")
        for addressee in effect.addressees:
            _entity(state, addressee)

    elif isinstance(effect, fx.SetRule):
        if not _RULE_KEY.fullmatch(effect.key) or "__" in effect.key:
            raise EffectError(f"invalid rule key: {effect.key}")
        if effect.value is None:
            state.rules.pop(effect.key, None)
        else:
            state.rules[effect.key] = effect.value

    elif isinstance(effect, fx.AdvanceTime):
        state.sim_time = state.sim_time + timedelta(minutes=effect.minutes)

    elif isinstance(effect, fx.SetTiles):
        _set_tiles(state, effect)

    elif isinstance(effect, fx.SetPosition):
        _set_position(state, effect)

    else:
        raise EffectError(f"unsupported effect: {type(effect).__name__}")


def _set_tiles(state: WorldState, effect) -> None:
    import hashlib

    from tinyworld.core.state import CHUNK, TERRAIN, Chunk

    for tile in effect.tiles:
        if tile.terrain not in TERRAIN:
            raise EffectError(f"unknown terrain {tile.terrain!r}")
    for region in effect.regions:
        _place(state, region.place)
    painted: dict[str, list[str]] = {}
    for tile in effect.tiles:
        key = f"{tile.x // CHUNK},{tile.y // CHUNK}"
        chunk = state.grid.get(key)
        painted.setdefault(key, list(chunk.terrain if chunk else Chunk().terrain))
        painted[key][(tile.y % CHUNK) * CHUNK + (tile.x % CHUNK)] = tile.terrain
    for key, cells in painted.items():
        chunk = state.grid.get(key) or Chunk()
        state.grid[key] = chunk.model_copy(update={"terrain": "".join(cells)})
    for region in effect.regions:
        # A region is kept in every chunk it touches, so a lookup needs one chunk only.
        for cy in range(region.y0 // CHUNK, region.y1 // CHUNK + 1):
            for cx in range(region.x0 // CHUNK, region.x1 // CHUNK + 1):
                key = f"{cx},{cy}"
                chunk = state.grid.get(key) or Chunk()
                state.grid[key] = chunk.model_copy(update={"regions": [*chunk.regions, region.model_copy()]})
    digest = hashlib.sha1(f"{state.grid_rev}|{effect.model_dump_json()}".encode()).hexdigest()
    state.grid_rev = int(digest[:12], 16)


def _set_position(state: WorldState, effect) -> None:
    from tinyworld.world import grid

    entity = _entity(state, effect.entity)
    if entity.kind == "place":
        raise EffectError("places cannot be moved")
    if not state.grid:
        raise EffectError("this world has no tile map")
    terrain = grid.terrain_at(state, effect.x, effect.y)
    if terrain is None:
        raise EffectError(f"({effect.x}, {effect.y}) has not been generated")
    if not grid.walkable(state, effect.x, effect.y):
        raise EffectError(f"({effect.x}, {effect.y}) cannot be walked on")
    place = grid.place_at(state, effect.x, effect.y)
    if place is None:
        raise EffectError(f"({effect.x}, {effect.y}) belongs to no place")
    before = grid.position_of(entity)
    if before is not None and grid.distance(before, (effect.x, effect.y)) > grid.MAX_STEP:
        raise EffectError("that is too far to walk in one go")
    entity.attrs["x"] = effect.x
    entity.attrs["y"] = effect.y
    entity.location = place


def _arrive(state: WorldState, entity, place: str) -> None:
    """On a tile map a person who is moved to a place stands somewhere in it."""
    from tinyworld.world import grid

    spot = grid.entrance(state, place, grid.occupied(state) - {grid.position_of(entity)})
    if spot is None:
        entity.attrs.pop("x", None)
        entity.attrs.pop("y", None)
    else:
        entity.attrs["x"], entity.attrs["y"] = spot


def end_time(state: WorldState, effects: Iterable):
    """The time at which an event with these effects is over."""
    minutes = sum(e.minutes for e in effects if isinstance(e, fx.AdvanceTime))
    return state.sim_time + timedelta(minutes=minutes)


def apply_effects(
    state: WorldState,
    effects: Iterable,
    registry: AttrRegistry = REGISTRY,
) -> WorldState:
    """Apply effects to a copy. The input state is untouched on failure."""
    working = state.model_copy(deep=True)
    for effect in effects:
        apply_effect(working, effect, registry)
    return working


def apply_event_in_place(
    state: WorldState,
    event: Event,
    registry: AttrRegistry = REGISTRY,
) -> None:
    """Apply a stored event. Only for replaying a log already known to be valid."""
    if event.seq != state.seq + 1:
        raise EffectError(f"event {event.seq} does not follow state {state.seq}")
    for effect in event.effects:
        apply_effect(state, effect, registry)
    # An event is stamped with the time at which it is over, so "everything
    # up to time T" is a prefix of the log.
    if event.sim_time != state.sim_time:
        raise EffectError("event time does not match the state it produces")
    state.seq = event.seq


def apply_event(
    state: WorldState,
    event: Event,
    registry: AttrRegistry = REGISTRY,
) -> WorldState:
    """Apply an event atomically: all of its effects or none."""
    working = state.model_copy(deep=True)
    apply_event_in_place(working, event, registry)
    return working


def fold(
    initial: WorldState,
    events: Iterable[Event],
    registry: AttrRegistry = REGISTRY,
) -> WorldState:
    state = initial.model_copy(deep=True)
    for event in events:
        apply_event_in_place(state, event, registry)
    return state
