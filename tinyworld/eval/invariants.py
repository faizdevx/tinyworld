"""Invariants every event log must satisfy, checked independently of the reducers.

The reducers refuse structurally invalid effects. These checks look at what a
whole event means: who did it, whether they could, and whether quantities add
up. They run over a stored log, and on every commit when debugging is on.
"""

from dataclasses import dataclass

from tinyworld.core import effects as fx
from tinyworld.core.events import SYSTEM_ACTORS, Event
from tinyworld.core.reducers import apply_event_in_place
from tinyworld.core.state import WorldState
from tinyworld.core.store import Store


@dataclass(frozen=True)
class Violation:
    seq: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"event {self.seq}: {self.rule}: {self.detail}"


def _totals(state: WorldState) -> dict[str, int]:
    totals: dict[str, int] = {}
    for entity in state.entities.values():
        for item, quantity in entity.inventory.items():
            totals[item] = totals.get(item, 0) + quantity
    return totals


def _declared_changes(before: WorldState, event: Event) -> dict[str, int]:
    """Net change in each item's total that the event's effects account for."""
    changes: dict[str, int] = {}
    for effect in event.effects:
        if isinstance(effect, fx.ChangeQuantity):
            changes[effect.item] = changes.get(effect.item, 0) + effect.delta
        elif isinstance(effect, fx.CreateEntity):
            for item, quantity in effect.entity.inventory.items():
                changes[item] = changes.get(item, 0) + quantity
        elif isinstance(effect, fx.RemoveEntity):
            gone = before.entities.get(effect.entity)
            if gone is None:
                continue
            for item, quantity in gone.inventory.items():
                changes[item] = changes.get(item, 0) - quantity
            if gone.kind in ("item", "resource"):
                # Removing a kind of thing removes every instance of it.
                changes[gone.id] = -_totals(before).get(gone.id, 0)
    return changes


def check_event(before: WorldState, event: Event, after: WorldState) -> list[Violation]:
    """Violations in one event, given the state on either side of it."""
    found: list[Violation] = []

    def violation(rule: str, detail: str) -> None:
        found.append(Violation(event.seq, rule, detail))

    if event.seq != before.seq + 1:
        violation("sequence", f"follows {before.seq}")
    if event.sim_time < before.sim_time:
        violation("time", "time ran backwards")
    for cause in event.causes:
        if not 0 < cause < event.seq:
            violation("causality", f"cause {cause} does not precede the event")

    actor = before.entities.get(event.actor)
    if event.actor not in SYSTEM_ACTORS:
        if actor is None:
            # An actor may be created by the very event that introduces them.
            if event.actor not in after.entities:
                violation("actor", f"{event.actor} does not exist")
        elif actor.kind == "person" and not actor.alive:
            violation("dead actor", f"{actor.name} acted after dying")

    for effect in event.effects:
        if isinstance(effect, fx.Utter):
            speaker = before.entities.get(effect.speaker)
            if speaker is not None and not speaker.alive:
                violation("dead actor", f"{speaker.name} spoke after dying")
        if (
            isinstance(effect, fx.MoveEntity)
            and event.kind in ("action", "utterance")
            and effect.entity == event.actor
        ):
            mover = before.entities.get(effect.entity)
            if mover is not None and mover.location is not None:
                if before.path(mover.location, effect.to) is None:
                    violation(
                        "movement",
                        f"{mover.name} moved to {effect.to} with no route from {mover.location}",
                    )

    for person in after.people(alive=False):
        location = person.location
        if location is not None and (
            location not in after.entities or after.entities[location].kind != "place"
        ):
            violation("location", f"{person.name} is at {location}, which is not a place")

    if after.grid:
        from tinyworld.world import grid

        stood = {}
        for person in after.people():
            spot = grid.position_of(person)
            if spot is None:
                continue
            if not grid.walkable(after, *spot):
                violation("position", f"{person.name} stands on ground that cannot be walked on {spot}")
            elif grid.place_at(after, *spot) != person.location:
                violation("position", f"{person.name} is at {person.location} but stands in {grid.place_at(after, *spot)}")
            stood.setdefault(spot, []).append(person.name)
        for spot, names in stood.items():
            if len(names) > 3:
                violation("position", f"{len(names)} people crowd one tile {spot}")
        for effect in event.effects:
            if isinstance(effect, fx.SetPosition):
                moved = before.entities.get(effect.entity)
                start = grid.position_of(moved) if moved is not None else None
                if start is not None and grid.distance(start, (effect.x, effect.y)) > grid.MAX_STEP:
                    violation("movement", f"{effect.entity} jumped farther than anyone can walk")

    before_totals, after_totals = _totals(before), _totals(after)
    declared = _declared_changes(before, event)
    for item in set(before_totals) | set(after_totals) | set(declared):
        actual = after_totals.get(item, 0) - before_totals.get(item, 0)
        if actual != declared.get(item, 0):
            violation(
                "conservation",
                f"{item} changed by {actual}, but effects account for {declared.get(item, 0)}",
            )
    return found


def check_log(store: Store, branch_id: str, *, limit: int = 200) -> list[Violation]:
    """Replay a branch from nothing and collect every violation, up to ``limit``."""
    state = store.initial_state(branch_id)
    found: list[Violation] = []
    for event in store.events(branch_id):
        before = state.model_copy(deep=True)
        try:
            apply_event_in_place(state, event)
        except ValueError as exc:
            found.append(Violation(event.seq, "replay", str(exc)))
            break
        found += check_event(before, event, state)
        if len(found) >= limit:
            break
    return found
