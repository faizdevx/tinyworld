"""The tile world: geometry that is derived from state, never stored twice.

Places stay entities. A place gets a *footprint* (the tiles of its regions) and
doors (door tiles inside it). The place graph that routines and ``state.path``
use is derived from adjacency: a building meets a street at its door, a street
block meets the next along a road.

Everything here is a pure function of ``WorldState``.
"""

import heapq
from collections import OrderedDict

from tinyworld.core.state import (
    CHUNK, DOOR, FLOOR, GROUND, ROAD, WALKABLE, WALL, Region, WorldState,
)

# How far a person walks in a minute, and how far they see and hear.
TILES_PER_MINUTE = 6
SIGHT = 14
HEARING = 8
# Each wall between two people costs this much of the hearing range.
WALL_MUFFLE = 4
TALK_RANGE = 4
MAX_STEP = 64  # tiles one SetPosition may cover (a leg of a walk)


def chunk_of(x: int, y: int) -> tuple[int, int]:
    return x // CHUNK, y // CHUNK


def key_of(cx: int, cy: int) -> str:
    return f"{cx},{cy}"


def known_chunk(state: WorldState, cx: int, cy: int) -> bool:
    return key_of(cx, cy) in state.grid


def has_grid(state: WorldState) -> bool:
    return bool(state.grid)


def terrain_at(state: WorldState, x: int, y: int) -> str | None:
    """The terrain character on a tile, or None if that chunk was never generated."""
    chunk = state.grid.get(key_of(*chunk_of(x, y)))
    if chunk is None:
        return None
    return chunk.terrain[(y % CHUNK) * CHUNK + (x % CHUNK)]


def place_at(state: WorldState, x: int, y: int) -> str | None:
    """The place that owns a tile. The latest region that contains it wins."""
    chunk = state.grid.get(key_of(*chunk_of(x, y)))
    if chunk is None:
        return None
    for region in reversed(chunk.regions):
        if region.has(x, y):
            return region.place
    return None


def regions_of(state: WorldState, place: str) -> list[Region]:
    seen, out = set(), []
    for chunk in state.grid.values():
        for region in chunk.regions:
            if region.place == place:
                key = (region.x0, region.y0, region.x1, region.y1)
                if key not in seen:
                    seen.add(key)
                    out.append(region)
    return out


def footprint(state: WorldState, place: str) -> list[tuple[int, int]]:
    """Every tile the place owns, in order. A tile covered by a later region of another place is not it."""
    tiles = []
    for region in regions_of(state, place):
        for y in range(region.y0, region.y1 + 1):
            for x in range(region.x0, region.x1 + 1):
                if place_at(state, x, y) == place:
                    tiles.append((x, y))
    return sorted(set(tiles), key=lambda t: (t[1], t[0]))


def doors(state: WorldState, place: str) -> list[tuple[int, int]]:
    return [t for t in footprint(state, place) if terrain_at(state, *t) == DOOR]


def walkable(state: WorldState, x: int, y: int) -> bool:
    return terrain_at(state, x, y) in WALKABLE


def passable(state: WorldState, x: int, y: int) -> bool:
    """Walkable ground that belongs to some place: where a person can stand."""
    return walkable(state, x, y) and place_at(state, x, y) is not None


def position_of(entity) -> tuple[int, int] | None:
    x, y = entity.attrs.get("x"), entity.attrs.get("y")
    if isinstance(x, int) and isinstance(y, int) and not isinstance(x, bool) and not isinstance(y, bool):
        return x, y
    return None


def occupied(state: WorldState) -> set[tuple[int, int]]:
    return {p for e in state.entities.values() if e.kind == "person" and e.alive and (p := position_of(e))}


def entrance(state: WorldState, place: str, taken: set[tuple[int, int]] | None = None) -> tuple[int, int] | None:
    """A free walkable tile inside the place, nearest its door; None if it has no footprint."""
    taken = taken or set()
    tiles = [t for t in footprint(state, place) if walkable(state, *t)]
    if not tiles:
        return None
    gates = doors(state, place) or tiles[:1]

    def near(t):
        return min(abs(t[0] - d[0]) + abs(t[1] - d[1]) for d in gates)

    inside = [t for t in tiles if t not in taken] or tiles
    return min(inside, key=lambda t: (near(t), t[1], t[0]))


# -- paths ------------------------------------------------------------------

_CACHE: "OrderedDict[tuple, tuple | None]" = OrderedDict()
_CACHE_SIZE = 4096


def find_path(state: WorldState, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]] | None:
    """A shortest 4-connected walk over walkable tiles, start and goal included. Cached per terrain revision."""
    if not (passable(state, *start) and passable(state, *goal)):
        return None
    # grid_rev is a hash chain of every terrain patch, so equal revisions mean equal terrain.
    key = (state.grid_rev, start, goal)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        hit = _CACHE[key]
        return list(hit) if hit is not None else None
    path = _astar(state, start, goal)
    _CACHE[key] = tuple(path) if path is not None else None
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return path


def _astar(state, start, goal, limit: int = 60000):
    if start == goal:
        return [start]
    open_ = [(0, 0, start)]
    best = {start: 0}
    came: dict = {}
    expanded = 0
    while open_:
        _, cost, node = heapq.heappop(open_)
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(came[path[-1]])
            return path[::-1]
        if cost > best.get(node, cost):
            continue
        expanded += 1
        if expanded > limit:
            return None
        x, y = node
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not passable(state, nx, ny):
                continue
            step = cost + (1 if terrain_at(state, nx, ny) == ROAD else 2 if terrain_at(state, nx, ny) == GROUND else 1)
            if step < best.get((nx, ny), 1 << 30):
                best[(nx, ny)] = step
                came[(nx, ny)] = node
                heapq.heappush(open_, (step + abs(nx - goal[0]) + abs(ny - goal[1]), step, (nx, ny)))
    return None


# -- senses -----------------------------------------------------------------


def line(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Bresenham's line from a to b, both included."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    out = []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def walls_between(state: WorldState, a: tuple[int, int], b: tuple[int, int]) -> int:
    return sum(1 for t in line(a, b)[1:-1] if terrain_at(state, *t) == WALL)


def distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def sees(state: WorldState, a: tuple[int, int], b: tuple[int, int], radius: int = SIGHT) -> bool:
    """Within the radius, with no wall on the line between."""
    return distance(a, b) <= radius and walls_between(state, a, b) == 0


def hears(state: WorldState, a: tuple[int, int], b: tuple[int, int], loud: bool = False) -> bool:
    """Speech carries a short way, a shout further; each wall takes some of it."""
    reach = HEARING * (2 if loud else 1) - WALL_MUFFLE * walls_between(state, a, b)
    return distance(a, b) <= reach


def nearby(state: WorldState, person, radius: int = SIGHT) -> list[tuple[object, int]]:
    """(other person, distance) for everyone this person can see, nearest first."""
    me = position_of(person)
    if me is None:
        return []
    found = []
    for other in state.people():
        if other.id == person.id:
            continue
        there = position_of(other)
        if there is not None and sees(state, me, there, radius):
            found.append((other, distance(me, there)))
    return sorted(found, key=lambda t: (t[1], t[0].id))


def can_talk(state: WorldState, a, b) -> bool:
    """Two people can talk if they share a place, or stand close with a clear line."""
    if a.location == b.location:
        return True
    pa, pb = position_of(a), position_of(b)
    return pa is not None and pb is not None and distance(pa, pb) <= TALK_RANGE and walls_between(state, pa, pb) == 0


# -- the place graph, derived ----------------------------------------------


def adjacency(state: WorldState) -> dict[tuple[str, str], int]:
    """Places that touch, and how many tiles apart their nearest touching tiles lie: {(a, b): tiles}.

    Two places touch where a walkable tile of one is next to a walkable tile of the other.
    """
    touching: dict[tuple[str, str], int] = {}
    for key, chunk in state.grid.items():
        cx, cy = (int(n) for n in key.split(","))
        for ly in range(CHUNK):
            for lx in range(CHUNK):
                if chunk.terrain[ly * CHUNK + lx] not in WALKABLE:
                    continue
                x, y = cx * CHUNK + lx, cy * CHUNK + ly
                here = place_at(state, x, y)
                if here is None:
                    continue
                for nx, ny in ((x + 1, y), (x, y + 1)):
                    if not walkable(state, nx, ny):
                        continue
                    there = place_at(state, nx, ny)
                    if there is not None and there != here:
                        pair = tuple(sorted((here, there)))
                        touching[pair] = 1
    return touching
