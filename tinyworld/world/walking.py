"""Walking: moving over the tile map takes time, and can be interrupted.

A move to a place becomes a *route*: ``attrs["route"] = {"to": place}``. Each leg
walks up to ``LEG_MINUTES`` of the way (a ``SetPosition``), so on the way other
people see the walker and the walker can be stopped, spoken to, or can change
their mind. The path is not stored; each leg finds it again from where the
walker stands (the finder caches per terrain revision).

Doing anything but walking drops the route (see ``gm/master.outcome_draft``).
"""

import math

from tinyworld.core import effects as fx
from tinyworld.core.state import Entity, WorldState
from tinyworld.world import grid

LEG_MINUTES = 5


def route_of(person: Entity) -> str | None:
    route = person.attrs.get("route")
    if isinstance(route, dict) and isinstance(route.get("to"), str):
        return route["to"]
    return None


def route_tile(person: Entity) -> tuple[int, int] | None:
    """The tile a route is heading for, when it is heading for a tile and not a place."""
    route = person.attrs.get("route")
    tile = route.get("tile") if isinstance(route, dict) else None
    if isinstance(tile, list) and len(tile) == 2 and all(isinstance(n, int) for n in tile):
        return tile[0], tile[1]
    return None


def stop_effects(person: Entity) -> list:
    return [fx.SetAttr(entity=person.id, key="route", value=None)] if route_of(person) else []


def _leg(state: WorldState, person: Entity, dest: str, started: bool, tile=None, label: str = "") -> tuple[list, str, int] | str:
    here = grid.position_of(person)
    goal = tile or grid.entrance(state, dest, grid.occupied(state) - {here})
    if goal is None:
        return f"{state.entities[dest].name} has no place on the map"
    path = grid.find_path(state, here, goal)
    if path is None:
        return f"there is no way to {state.entities[dest].name} from here"
    if len(path) == 1:
        return [], "", 0
    tiles = grid.TILES_PER_MINUTE * LEG_MINUTES
    index = min(len(path) - 1, tiles)
    step = path[index]
    minutes = max(1, math.ceil(index / grid.TILES_PER_MINUTE))
    name = label or state.entities[dest].name
    effects: list = [fx.SetPosition(entity=person.id, x=step[0], y=step[1])]
    if index == len(path) - 1:
        effects.append(fx.SetAttr(entity=person.id, key="route", value=None))
        narration = f"{person.name} arrives at {name}."
    else:
        route = {"to": dest} if tile is None else {"to": dest, "tile": [tile[0], tile[1]]}
        effects.append(fx.SetAttr(entity=person.id, key="route", value=route))
        narration = (
            f"{person.name} sets out for {name}." if started else f"{person.name} walks on towards {name}."
        )
    return effects, narration, minutes


def step(state: WorldState, person: Entity, dest: str, resume: bool = False) -> tuple[list, str, int] | str:
    """The next leg of the way to ``dest``, or why it cannot be walked."""
    if grid.position_of(person) is None:
        return "not standing anywhere on the map"
    target = state.entities.get(dest)
    if target is None or target.kind != "place":
        return "that is not a place"
    current = route_of(person)
    tile = route_tile(person) if current == dest else None
    leg = _leg(state, person, dest, started=not (resume or current == dest), tile=tile,
               label="the edge of the known ground" if tile else "")
    if isinstance(leg, str):
        return leg
    effects, narration, minutes = leg
    if not effects:
        return f"already at {target.name}"
    return effects, narration, minutes


def explore(state: WorldState, person: Entity, direction: str) -> tuple[list, str, int] | str:
    """Set out for the edge of the known ground on one side."""
    from tinyworld.world import frontier

    if direction not in frontier.DIRECTIONS:
        return "explore north, south, east or west"
    here = grid.position_of(person)
    if here is None:
        return "not standing anywhere on the map"
    edge = frontier.nearest_edge(state, here, direction)
    if edge is None:
        return f"there is nothing unexplored to the {direction}"
    place = grid.place_at(state, *edge)
    if place is None:
        return "the edge cannot be reached"
    leg = _leg(state, person, place, started=True, tile=edge, label="the edge of the known ground")
    if isinstance(leg, str):
        return leg
    effects, narration, minutes = leg
    if not effects:
        return "already at the edge"
    if "sets out" in narration:
        narration = f"{person.name} sets out for the unexplored ground to the {direction}."
    return effects, narration, minutes


def where_is(state: WorldState, person: Entity) -> str:
    """A line for prompts: where the person stands and whether they are on their way somewhere."""
    spot = grid.position_of(person)
    if spot is None:
        return ""
    dest = route_of(person)
    base = f"You stand at tile ({spot[0]}, {spot[1]})."
    if dest and dest in state.entities:
        goal = grid.entrance(state, dest)
        if goal:
            left = grid.distance(spot, goal)
            return base + f" You are on your way to {state.entities[dest].name}, about {math.ceil(left / grid.TILES_PER_MINUTE)} minutes off."
    return base
