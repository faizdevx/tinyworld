"""From a place graph to a tile map.

Genesis gives places, links and travel minutes. This turns them into tiles:
buildings get walls, a floor and a door that faces the road; open places (a
square, a market, a farm) get ground; small rooms are built onto the building
they belong to; roads join door to door; and every road tile belongs to a
*street block*, a small place of its own, so someone walking outdoors is always
somewhere in particular.

The result is a list of ordinary event drafts (``SetTiles``, ``SetEdge``,
``SetPosition``), so a laid-out world replays like any other. The layout is a
pure function of the state it is given: same graph, same map.
"""

import heapq
import math
from dataclasses import dataclass

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.ids import edge_key, make_id
from tinyworld.core.reducers import apply_effect
from tinyworld.core.state import (
    CHUNK, DOOR, FIELD, FLOOR, GROUND, ROAD, WALL, Entity, PlaceEdge, Region, WorldState,
)
from tinyworld.world import grid

BLOCK = 8  # a street block is 8 by 8 tiles
BLOCK_PREFIX = "place:blk_"
WILD_PREFIX = "place:wild_"
MARGIN = 4  # clear tiles kept between buildings, for roads
OPEN_WORDS = (
    "square", "market", "field", "farm", "yard", "park", "ghat", "stall", "stand",
    "road", "street", "bazaar", "chowk", "station", "garden", "plaza", "ground", "bridge",
)
FIELD_WORDS = ("farm", "field", "paddy", "orchard")
BIG_WORDS = ("hall", "works", "factory", "church", "school", "mill", "office", "palace", "fort", "inn", "tech park", "workshop")
SMALL_WORDS = ("stall", "stand", "kiosk", "booth", "shed")


@dataclass
class Plot:
    place: str
    w: int
    h: int
    open: bool
    field: bool = False
    x: int = 0  # top-left corner
    y: int = 0
    door_side: str = "s"  # which side the door is on: n e s w
    room_of: str | None = None

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def rect(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.w - 1, self.y + self.h - 1


def _words(entity: Entity) -> str:
    return (entity.name + " " + str(entity.attrs.get("place_type", ""))).lower()


def is_open(entity: Entity) -> bool:
    # "enclosed" is only certain when true; a default of false says nothing about the sky.
    if entity.attrs.get("enclosed") is True:
        return False
    return any(w in _words(entity) for w in OPEN_WORDS)


def size_of(state: WorldState, entity: Entity) -> tuple[int, int]:
    text = _words(entity)
    people = len(state.people_at(entity.id))
    if is_open(entity):
        if any(w in text for w in FIELD_WORDS):
            return 16, 11
        if any(w in text for w in SMALL_WORDS):
            return 8, 6
        return 12, 9
    if any(w in text for w in SMALL_WORDS):
        return 6, 5
    w, h = (10, 8) if any(w in text for w in BIG_WORDS) else (8, 6)
    while (w - 2) * (h - 2) < 2 * people + 4:
        w += 1
        h += 1
    return w, h


def _graph(state: WorldState):
    places = sorted(e.id for e in state.entities.values() if e.kind == "place" and not e.id.startswith((BLOCK_PREFIX, WILD_PREFIX)))
    edges: dict[str, dict[str, int]] = {p: {} for p in places}
    for key, edge in state.edges.items():
        a, b = key.split("|")
        if a in edges and b in edges:
            edges[a][b] = edge.travel_minutes
            edges[b][a] = edge.travel_minutes
    return places, edges


def _rooms(state: WorldState, places, edges) -> dict[str, str]:
    """Small enclosed places with a single close neighbour are rooms of that neighbour."""
    rooms = {}
    for p in places:
        e = state.entities[p]
        if e.attrs.get("enclosed") is True and len(edges[p]) == 1:
            (parent, minutes), = edges[p].items()
            if minutes <= 2:
                rooms[p] = parent
    # A room of a room is a room of the building that holds them both.
    for r, parent in list(rooms.items()):
        while parent in rooms:
            parent = rooms[parent]
        rooms[r] = parent
    return rooms


def _separate(boxes: dict[str, list[int]], rounds: int = 120) -> None:
    """Push overlapping boxes [x, y, w, h] apart until each has MARGIN clear tiles around it."""
    names = sorted(boxes)
    for _ in range(rounds):
        moved = False
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ba, bb = boxes[a], boxes[b]
                dx = (bb[0] + bb[2] / 2) - (ba[0] + ba[2] / 2)
                dy = (bb[1] + bb[3] / 2) - (ba[1] + ba[3] / 2)
                need_x = (ba[2] + bb[2]) / 2 + MARGIN
                need_y = (ba[3] + bb[3]) / 2 + MARGIN
                if abs(dx) < need_x and abs(dy) < need_y:
                    moved = True
                    if need_x - abs(dx) < need_y - abs(dy):
                        push = math.ceil((need_x - abs(dx)) / 2)
                        sign = 1 if dx >= 0 else -1
                        ba[0] -= sign * push
                        bb[0] += sign * push
                    else:
                        push = math.ceil((need_y - abs(dy)) / 2)
                        sign = 1 if dy >= 0 else -1
                        ba[1] -= sign * push
                        bb[1] += sign * push
        if not moved:
            return


def _room_rect(host: Plot, side: str, w: int, h: int, n: int) -> tuple[int, int]:
    """Top-left of the n-th room built onto ``host`` on ``side``, sharing the host's wall."""
    if side in ("e", "w"):
        x = host.x + host.w - 1 if side == "e" else host.x - w + 1
        return x, host.y + n * (h - 1)
    y = host.y + host.h - 1 if side == "s" else host.y - h + 1
    return host.x + n * (w - 1), y


def plan(state: WorldState) -> tuple[dict[str, Plot], dict[str, str], dict[str, dict[str, int]]]:
    """Where every place goes. Returns (plots, rooms, edges among all places)."""
    places, edges = _graph(state)
    rooms = _rooms(state, places, edges)
    main = [p for p in places if p not in rooms]
    hub = max(main, key=lambda p: (len([n for n in edges[p] if n not in rooms]), -main.index(p)))
    plots: dict[str, Plot] = {}
    for p in main:
        w, h = size_of(state, state.entities[p])
        plots[p] = Plot(p, w, h, is_open(state.entities[p]), field=any(x in _words(state.entities[p]) for x in FIELD_WORDS))

    # A tree out of the hub; each place sits at its minutes' walk from its parent, pointing outward.
    depth = {hub: 0}
    parent: dict[str, str] = {}
    order = [hub]
    for node in order:
        for other in sorted(edges[node]):
            if other in rooms or other in depth:
                continue
            depth[other] = depth[node] + 1
            parent[other] = node
            order.append(other)
    for p in main:  # places no path reaches hang off the hub
        if p not in depth:
            depth[p] = 1
            parent[p] = hub
            order.append(p)
    children: dict[str, list[str]] = {}
    for p in order[1:]:
        children.setdefault(parent[p], []).append(p)
    heading = {hub: 0.0}
    for node in order:
        kids = children.get(node, [])
        for i, kid in enumerate(kids):
            if node == hub:
                angle = 2 * math.pi * i / max(1, len(kids)) + 0.4
            else:
                angle = heading[node] + (i - (len(kids) - 1) / 2) * 0.9
            heading[kid] = angle
            minutes = edges[node].get(kid, 5)
            dist = max(minutes * grid.TILES_PER_MINUTE, (plots[node].w + plots[kid].w) / 2 + MARGIN + 2)
            plots[kid].x = round(plots[node].cx + math.cos(angle) * dist - plots[kid].w / 2)
            plots[kid].y = round(plots[node].cy + math.sin(angle) * dist - plots[kid].h / 2)
    # Doors face the parent.
    for p, plot in plots.items():
        if p == hub:
            plot.door_side = "s"
            continue
        a = plots[parent[p]]
        dx, dy = a.cx - plot.cx, a.cy - plot.cy
        plot.door_side = ("e" if dx > 0 else "w") if abs(dx) >= abs(dy) else ("s" if dy > 0 else "n")

    # Rooms are built onto the side of the building away from its door.
    members: dict[str, list[str]] = {}
    for room, host in sorted(rooms.items()):
        members.setdefault(host, []).append(room)
    annex: dict[str, Plot] = {}
    for host, names in members.items():
        h_plot = plots[host]
        side = {"s": "n", "n": "s", "e": "w", "w": "e"}[h_plot.door_side]
        for n, room in enumerate(names):
            w, h = size_of(state, state.entities[room])
            w, h = min(w, 6), min(h, 5)
            x, y = _room_rect(h_plot, side, w, h, n)
            annex[room] = Plot(room, w, h, False, x=x, y=y, door_side=side, room_of=host)

    # Separate each building together with its rooms, as one box.
    boxes: dict[str, list[int]] = {}
    for p, plot in plots.items():
        mine = [plot] + [annex[r] for r in members.get(p, [])]
        x0 = min(q.x for q in mine)
        y0 = min(q.y for q in mine)
        x1 = max(q.x + q.w for q in mine)
        y1 = max(q.y + q.h for q in mine)
        boxes[p] = [x0, y0, x1 - x0, y1 - y0]
    origin = {p: (b[0], b[1]) for p, b in boxes.items()}
    _separate(boxes)
    for p, plot in plots.items():
        dx, dy = boxes[p][0] - origin[p][0], boxes[p][1] - origin[p][1]
        plot.x += dx
        plot.y += dy
        for r in members.get(p, []):
            annex[r].x += dx
            annex[r].y += dy
    plots.update(annex)
    return plots, rooms, edges


# -- painting ----------------------------------------------------------------


def _normalise(plots: dict[str, Plot]) -> None:
    left = min(p.x for p in plots.values())
    top = min(p.y for p in plots.values())
    for p in plots.values():
        p.x += CHUNK - left
        p.y += CHUNK - top


def _door_tile(plot: Plot) -> tuple[int, int]:
    x0, y0, x1, y1 = plot.rect()
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    return {"n": (cx, y0), "s": (cx, y1), "w": (x0, cy), "e": (x1, cy)}[plot.door_side]


def _outside(plot: Plot, door: tuple[int, int]) -> tuple[int, int]:
    dx, dy = {"n": (0, -1), "s": (0, 1), "w": (-1, 0), "e": (1, 0)}[plot.door_side]
    return door[0] + dx, door[1] + dy


def _route(blocked: set, roads: set, start, goal, box) -> list[tuple[int, int]] | None:
    x0, y0, x1, y1 = box
    open_ = [(0, 0, start)]
    best = {start: 0}
    came: dict = {}
    while open_:
        _, cost, node = heapq.heappop(open_)
        if node == goal:
            path = [goal]
            while path[-1] != start:
                path.append(came[path[-1]])
            return path[::-1]
        if cost > best.get(node, cost):
            continue
        x, y = node
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (x0 <= nx <= x1 and y0 <= ny <= y1) or (nx, ny) in blocked and (nx, ny) != goal:
                continue
            step = cost + (1 if (nx, ny) in roads else 3)
            if step < best.get((nx, ny), 1 << 30):
                best[(nx, ny)] = step
                came[(nx, ny)] = node
                heapq.heappush(open_, (step + abs(nx - goal[0]) + abs(ny - goal[1]), step, (nx, ny)))
    return None


def _ensure_shrine(state: WorldState) -> list:
    """Residents ask the god at a holy place. A world without one gets a shrine near its hub."""
    from tinyworld.world import petitions

    if petitions.holy_places(state):
        return []
    places, edges = _graph(state)
    if not places or "place:the_shrine" in state.entities:
        return []
    hub = max(places, key=lambda p: (len(edges[p]), p))
    return [
        fx.CreateEntity(entity=Entity(
            id="place:the_shrine", kind="place", name="The Shrine",
            attrs={"description": "A small shrine where people come to ask the god for help.", "place_type": "shrine"},
        )),
        fx.SetEdge(a="place:the_shrine", b=hub, edge=PlaceEdge(travel_minutes=4)),
    ]


def _paint(plots: dict[str, Plot]):
    """Terrain, wall tiles, regions and outside doors for a set of placed plots."""
    terrain: dict[tuple[int, int], str] = {}
    blocked: set[tuple[int, int]] = set()
    regions: list[tuple[str, tuple[int, int, int, int]]] = []
    doors: dict[str, tuple[int, int]] = {}

    for place, plot in sorted(plots.items()):
        x0, y0, x1, y1 = plot.rect()
        if plot.open:
            fill = FIELD if plot.field else GROUND
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    terrain[(x, y)] = fill
        else:
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    edge = x in (x0, x1) or y in (y0, y1)
                    terrain[(x, y)] = WALL if edge else FLOOR
                    if edge and plot.room_of is None:
                        blocked.add((x, y))
            if plot.room_of is None:
                door = _door_tile(plot)
                terrain[door] = DOOR
                doors[place] = door
        regions.append((place, plot.rect()))

    # A room opens onto its building through the wall they share. Done last, so no wall paints over it.
    for place, plot in sorted(plots.items()):
        if plot.room_of is None:
            continue
        host = plots[plot.room_of]
        hx0, hy0, hx1, hy1 = host.rect()
        rx0, ry0, rx1, ry1 = plot.rect()
        if plot.door_side in ("e", "w"):
            wall_x = hx1 if plot.door_side == "e" else hx0
            lo, hi = max(hy0, ry0) + 1, min(hy1, ry1) - 1
            if hi >= lo:
                terrain[(wall_x, (lo + hi) // 2)] = DOOR
        else:
            wall_y = hy1 if plot.door_side == "s" else hy0
            lo, hi = max(hx0, rx0) + 1, min(hx1, rx1) - 1
            if hi >= lo:
                terrain[((lo + hi) // 2, wall_y)] = DOOR
    return terrain, blocked, regions, doors


def layout(state: WorldState) -> list[EventDraft]:
    """Events that lay the world out on a grid: terrain, streets, derived edges, positions."""
    if state.grid:
        raise ValueError("this world already has a tile map")
    shrine = _ensure_shrine(state)
    if shrine:
        state = state.model_copy(deep=True)
        for effect in shrine:
            apply_effect(state, effect)
    plots, rooms, edges = plan(state)
    if not plots:
        return []
    _normalise(plots)

    terrain, blocked, regions, doors = _paint(plots)

    # Roads, door to door along the graph's edges (rooms are reached through their host).
    roads: set[tuple[int, int]] = set()
    xs = [t[0] for t in terrain]
    ys = [t[1] for t in terrain]
    box = (min(xs) - 6, min(ys) - 6, max(xs) + 6, max(ys) + 6)
    wired: set[tuple[str, str]] = set()
    for a in sorted(plots):
        for b in sorted(edges.get(a, {})):
            if b in rooms or a in rooms or b not in plots or tuple(sorted((a, b))) in wired:
                continue
            wired.add(tuple(sorted((a, b))))
            ends = []
            for p in (a, b):
                plot = plots[p]
                door = doors.get(p) or _door_tile(plot)
                ends.append(_outside(plot, door) if not plot.open else _edge_tile(plot, plots[b if p == a else a]))
            path = _route(blocked | {t for t in terrain if terrain[t] == WALL}, roads, ends[0], ends[1], box)
            if path is None:
                continue
            for t in path:
                if terrain.get(t) in (None, GROUND):
                    terrain[t] = ROAD
                roads.add(t)
    # A building's door must reach the road even when it has no edge of its own drawn yet.
    for place, door in doors.items():
        out = _outside(plots[place], door)
        if terrain.get(out) is None:
            terrain[out] = ROAD
            roads.add(out)

    # Street blocks: one place per 8 by 8 block that has road in it.
    streets: dict[tuple[int, int], str] = {}
    for x, y in sorted(roads):
        streets.setdefault((x // BLOCK, y // BLOCK), block_id(x // BLOCK, y // BLOCK))
    street_entities = [
        fx.CreateEntity(entity=Entity(
            id=pid, kind="place", name=f"Street {bx},{by}",
            attrs={"place_type": "street", "description": "A street.", "enclosed": False},
        ))
        for (bx, by), pid in sorted(streets.items())
    ]
    wild_entities, region_list = _wild({t for t in terrain} | {(x, y) for r in regions for x, y in ((r[1][0], r[1][1]), (r[1][2], r[1][3]))}, state)
    street_entities = wild_entities + street_entities
    region_list += [
        Region(place=pid, x0=bx * BLOCK, y0=by * BLOCK, x1=bx * BLOCK + BLOCK - 1, y1=by * BLOCK + BLOCK - 1)
        for (bx, by), pid in sorted(streets.items())
    ]
    # Open places claim their ground after the streets; buildings after that.
    for place, (x0, y0, x1, y1) in sorted(regions, key=lambda r: (not plots[r[0]].open, r[0])):
        region_list.append(Region(place=place, x0=x0, y0=y0, x1=x1, y1=y1))

    tiles = [fx.Tile(x=x, y=y, terrain=t) for (x, y), t in sorted(terrain.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    effects: list = list(street_entities)
    for i in range(0, len(tiles), 4000):
        effects.append(fx.SetTiles(tiles=tiles[i:i + 4000], regions=[]))
    for i in range(0, len(region_list), 200):
        effects.append(fx.SetTiles(tiles=[], regions=region_list[i:i + 200]))
    effects = list(shrine) + effects
    drafts = [EventDraft(kind="system", actor="system", visibility="god_only", effects=effects,
                         narration="The town is laid out on a map.")]

    # Edges are derived from where places touch; the bible's own links give way to them.
    working = state.model_copy(deep=True)
    for e in effects[len(shrine):]:
        apply_effect(working, e)
    old = [fx.SetEdge(a=k.split("|")[0], b=k.split("|")[1], edge=None) for k in sorted(state.edges)]
    new = []
    centre = {p: (plots[p].cx, plots[p].cy) for p in plots}
    for (a, b) in sorted(grid.adjacency(working)):
        ca = centre.get(a) or _street_centre(a)
        cb = centre.get(b) or _street_centre(b)
        minutes = max(1, round(math.dist(ca, cb) / grid.TILES_PER_MINUTE))
        new.append(fx.SetEdge(a=a, b=b, edge=PlaceEdge(travel_minutes=minutes)))
    drafts.append(EventDraft(kind="system", actor="system", visibility="god_only", effects=old + new,
                             narration="Places are joined where they touch."))

    # Everyone stands somewhere inside the place they were in.
    standing = []
    taken: set[tuple[int, int]] = set()
    for person in sorted(working.people(), key=lambda p: p.id):
        if person.location is None:
            continue
        spot = grid.entrance(working, person.location, taken)
        if spot is None:
            continue
        taken.add(spot)
        standing.append(fx.SetPosition(entity=person.id, x=spot[0], y=spot[1]))
    if standing:
        drafts.append(EventDraft(kind="system", actor="system", visibility="god_only", effects=standing,
                                 narration="People take their places."))
    return drafts


def _edge_tile(plot: Plot, towards: Plot) -> tuple[int, int]:
    """A tile on the rim of an open place, on the side facing ``towards``."""
    x0, y0, x1, y1 = plot.rect()
    dx, dy = towards.cx - plot.cx, towards.cy - plot.cy
    if abs(dx) >= abs(dy):
        return (x1 + 1, (y0 + y1) // 2) if dx > 0 else (x0 - 1, (y0 + y1) // 2)
    return ((x0 + x1) // 2, y1 + 1) if dy > 0 else ((x0 + x1) // 2, y0 - 1)


def _street_centre(place_id: str) -> tuple[float, float]:
    """The middle of a street block or of a stretch of open ground, in tiles."""
    if place_id.startswith(WILD_PREFIX):
        cx, cy = (_dec(n) for n in place_id.removeprefix(WILD_PREFIX).split("_"))
        return cx * CHUNK + CHUNK / 2, cy * CHUNK + CHUNK / 2
    bx, by = (_dec(n) for n in place_id.removeprefix(BLOCK_PREFIX).split("_"))
    return bx * BLOCK + BLOCK / 2, by * BLOCK + BLOCK / 2


def _enc(n: int) -> str:
    return str(n) if n >= 0 else f"m{-n}"


def _dec(text: str) -> int:
    return int(text) if not text.startswith("m") else -int(text[1:])


def wild_id(cx: int, cy: int) -> str:
    return f"{WILD_PREFIX}{_enc(cx)}_{_enc(cy)}"


def block_id(bx: int, by: int) -> str:
    return f"{BLOCK_PREFIX}{_enc(bx)}_{_enc(by)}"


def _wild(tiles, state: WorldState):
    """Open ground under every chunk that holds anything: where a walker may leave the roads."""
    chunks = sorted({(x // CHUNK, y // CHUNK) for x, y in tiles})
    entities, regions = [], []
    for cx, cy in chunks:
        pid = wild_id(cx, cy)
        if pid not in state.entities:
            entities.append(fx.CreateEntity(entity=Entity(
                id=pid, kind="place", name=f"Open ground {cx},{cy}",
                attrs={"place_type": "wild", "description": "Open ground.", "enclosed": False},
            )))
        regions.append(Region(place=pid, x0=cx * CHUNK, y0=cy * CHUNK, x1=cx * CHUNK + CHUNK - 1, y1=cy * CHUNK + CHUNK - 1))
    return entities, regions


# -- growing the map ------------------------------------------------------------


@dataclass
class NewPlace:
    """What the creators propose for a new stretch of ground."""

    name: str
    kind: str = ""
    description: str = ""
    people: list | None = None  # [{"name", "occupation", "age"}]

    def __post_init__(self):
        self.people = self.people or []


def _spec_entity(spec: NewPlace) -> Entity:
    attrs = {"description": spec.description or spec.name, "place_type": spec.kind or "building"}
    return Entity(id=make_id("place", spec.name), kind="place", name=spec.name, attrs=attrs)


def _anchor(state: WorldState, cx: int, cy: int):
    """Where the new chunk meets the old: a road tile (else any passable tile) just across its border.

    Returns (tile in the old chunk, tile in the new chunk), or None if it touches nothing.
    """
    best = None
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        if not grid.known_chunk(state, cx + dx, cy + dy):
            continue
        for i in range(CHUNK):
            if dx:
                old = ((cx + dx) * CHUNK + (CHUNK - 1 if dx < 0 else 0), cy * CHUNK + i)
                new = (cx * CHUNK + (0 if dx < 0 else CHUNK - 1), cy * CHUNK + i)
            else:
                old = (cx * CHUNK + i, (cy + dy) * CHUNK + (CHUNK - 1 if dy < 0 else 0))
                new = (cx * CHUNK + i, cy * CHUNK + (0 if dy < 0 else CHUNK - 1))
            if not grid.passable(state, *old):
                continue
            score = (0 if grid.terrain_at(state, *old) == ROAD else 1, i)
            if best is None or score < best[0]:
                best = (score, old, new)
    return None if best is None else (best[1], best[2])


def extend(state: WorldState, key: str, specs: list, entropy) -> list[EventDraft]:
    """Events that make chunk ``key`` real: the proposed places placed and walled, joined by road
    to the old map, with their people. Placement draws from ``entropy`` (recorded), so two runs
    grow different maps from the same proposal."""
    from tinyworld.world import frontier

    cx, cy = frontier.parse(key)
    if key in state.grid:
        raise ValueError(f"chunk {key} already exists")
    ground = _anchor(state, cx, cy)
    if ground is None:
        raise ValueError(f"chunk {key} does not touch the known world")
    _, border = ground
    x0, y0 = cx * CHUNK, cy * CHUNK

    taken_ids = set(state.entities)
    chosen: list[tuple[NewPlace, Entity]] = []
    for spec in specs:
        try:
            entity = _spec_entity(spec)
        except ValueError:
            continue
        if entity.id in taken_ids or any(entity.id == e.id for _, e in chosen):
            continue
        chosen.append((spec, entity))

    plots: dict[str, Plot] = {}
    for spec, entity in chosen:
        w, h = size_of(state, entity)
        w, h = min(w, 12), min(h, 9)
        placed = None
        for _ in range(40):
            x = x0 + 3 + entropy.randint("layout.x", 0, max(0, CHUNK - w - 6))
            y = y0 + 3 + entropy.randint("layout.y", 0, max(0, CHUNK - h - 6))
            clear = MARGIN // 2
            if all(
                x + w + clear < p.x or x - clear > p.x + p.w or y + h + clear < p.y or y - clear > p.y + p.h
                for p in plots.values()
            ):
                placed = (x, y)
                break
        if placed is None:
            continue  # no room left in this chunk
        plot = Plot(
            entity.id, w, h, is_open(entity),
            field=any(k in _words(entity) for k in FIELD_WORDS), x=placed[0], y=placed[1],
        )
        dx, dy = border[0] - plot.cx, border[1] - plot.cy
        plot.door_side = ("e" if dx > 0 else "w") if abs(dx) >= abs(dy) else ("s" if dy > 0 else "n")
        plots[entity.id] = plot

    terrain, blocked, regions, doors = _paint(plots) if plots else ({}, set(), [], {})
    walls = blocked | {t for t in terrain if terrain[t] == WALL}
    roads: set[tuple[int, int]] = set()
    box = (x0, y0, x0 + CHUNK - 1, y0 + CHUNK - 1)
    toward = Plot("", 1, 1, True, x=border[0], y=border[1])
    for place, plot in sorted(plots.items()):
        start = _outside(plot, doors[place]) if place in doors else _edge_tile(plot, toward)
        path = _route(walls, roads, start, border, box)
        if path is None:
            continue
        for t in path:
            if terrain.get(t) in (None, GROUND):
                terrain[t] = ROAD
            roads.add(t)
    terrain.setdefault(border, ROAD)
    roads.add(border)

    new_blocks: dict[tuple[int, int], str] = {}
    for x, y in sorted(roads):
        pid = block_id(x // BLOCK, y // BLOCK)
        if pid not in state.entities:
            new_blocks.setdefault((x // BLOCK, y // BLOCK), pid)
    wild_entities, wild_regions = _wild({(x0, y0)}, state)
    entities: list = list(wild_entities)
    entities += [fx.CreateEntity(entity=entity) for _, entity in chosen if entity.id in plots]
    entities += [
        fx.CreateEntity(entity=Entity(
            id=pid, kind="place", name=f"Street {bx},{by}",
            attrs={"place_type": "street", "description": "A street.", "enclosed": False},
        ))
        for (bx, by), pid in sorted(new_blocks.items())
    ]
    region_list: list[Region] = list(wild_regions)
    for (bx, by), pid in sorted(new_blocks.items()):
        region_list.append(
            Region(place=pid, x0=bx * BLOCK, y0=by * BLOCK, x1=bx * BLOCK + BLOCK - 1, y1=by * BLOCK + BLOCK - 1)
        )
    for place, (rx0, ry0, rx1, ry1) in sorted(regions, key=lambda r: (not plots[r[0]].open, r[0])):
        region_list.append(Region(place=place, x0=rx0, y0=ry0, x1=rx1, y1=ry1))
    tiles = [
        fx.Tile(x=x, y=y, terrain=t)
        for (x, y), t in sorted(terrain.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    ]
    effects: list = list(entities)
    effects += [fx.SetTiles(tiles=tiles[i:i + 4000], regions=[]) for i in range(0, len(tiles), 4000)]
    effects.append(fx.SetTiles(tiles=[], regions=region_list))
    names = ", ".join(e.name for _, e in chosen if e.id in plots) or "open country"
    drafts = [EventDraft(
        kind="system", actor="system", visibility="god_only", effects=effects,
        narration=f"New ground is opened up: {names}.",
    )]

    working = state.model_copy(deep=True)
    for e in effects:
        apply_effect(working, e)
    centre = {p: (plots[p].cx, plots[p].cy) for p in plots}
    joins = []
    for a, b in sorted(grid.adjacency(working)):
        if edge_key(a, b) in state.edges:
            continue
        ca = centre.get(a) or _centre_of(working, a)
        cb = centre.get(b) or _centre_of(working, b)
        minutes = max(1, round(math.dist(ca, cb) / grid.TILES_PER_MINUTE))
        joins.append(fx.SetEdge(a=a, b=b, edge=PlaceEdge(travel_minutes=minutes)))
    if joins:
        drafts.append(EventDraft(
            kind="system", actor="system", visibility="god_only", effects=joins,
            narration="The new ground is joined to the town.",
        ))

    # The people who live there, as background folk (tier 2) until events draw them in.
    people: list = []
    for spec, entity in chosen:
        if entity.id not in plots:
            continue
        for who in spec.people[:4]:
            name = str(who.get("name", "")).strip()
            if not name:
                continue
            try:
                pid = make_id("person", name)
            except ValueError:
                continue
            if pid in working.entities or pid in {p.entity.id for p in people}:
                continue
            attrs: dict = {"tier": 2, "occupation": str(who.get("occupation", ""))[:60]}
            age = who.get("age")
            if isinstance(age, int) and not isinstance(age, bool) and 0 <= age <= 110:
                attrs["age"] = age
            people.append(fx.CreateEntity(entity=Entity(id=pid, kind="person", name=name, location=entity.id, attrs=attrs)))
    if people:
        for eff in people:
            apply_effect(working, eff)
        standing, taken = [], set()
        for eff in people:
            spot = grid.entrance(working, eff.entity.location, taken)
            if spot:
                taken.add(spot)
                standing.append(fx.SetPosition(entity=eff.entity.id, x=spot[0], y=spot[1]))
        drafts.append(EventDraft(
            kind="system", actor="system", visibility="god_only", effects=people + standing,
            narration="People are living there: " + ", ".join(p.entity.name for p in people) + ".",
        ))
    return drafts


def _centre_of(state: WorldState, place_id: str) -> tuple[float, float]:
    if place_id.startswith((BLOCK_PREFIX, WILD_PREFIX)):
        return _street_centre(place_id)
    regions = grid.regions_of(state, place_id)
    if not regions:
        return 0.0, 0.0
    r = regions[0]
    return (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2


# -- a resident builds something ----------------------------------------------


def build_near(state: WorldState, owner: Entity, name: str, kind: str = "building", near: tuple[int, int] | None = None) -> list:
    """Effects for a new building the owner has finished, on free ground close to ``near``.

    The first free spot is taken, nearest first, so the same state gives the same building. The
    place is owned by ``owner``; its tiles, its entity and its joins to the places it touches are
    all effects, so the result is part of the log.
    """
    name = name.strip()[:60]
    entity = Entity(
        id=make_id("place", name), kind="place", name=name,
        attrs={"description": f"{name}, built by {owner.name}.", "place_type": kind, "owner": owner.id},
    )
    if entity.id in state.entities:
        entity = entity.model_copy(update={
            "id": f"{entity.id}_{sum(1 for e in state.entities if e.startswith(entity.id)) + 1}",
        })
    spot = near or grid.position_of(owner)
    if spot is None or not state.grid:
        return []
    w, h = size_of(state, entity)
    w, h = min(w, 8), min(h, 6)
    margin = 2

    def free(x0: int, y0: int) -> bool:
        for y in range(y0 - margin, y0 + h + margin):
            for x in range(x0 - margin, x0 + w + margin):
                if grid.terrain_at(state, x, y) not in (GROUND, FIELD):
                    return False
                here = grid.place_at(state, x, y)
                if here is None or not here.startswith((WILD_PREFIX, BLOCK_PREFIX)):
                    return False
                if any(e.kind == "person" and grid.position_of(e) == (x, y) for e in state.entities.values()):
                    return False
        return True

    found = None
    for r in range(4, 40):
        ring = [
            (spot[0] + dx, spot[1] + dy)
            for dx in range(-r, r + 1) for dy in range(-r, r + 1)
            if max(abs(dx), abs(dy)) == r
        ]
        for x, y in sorted(ring, key=lambda t: (t[1], t[0])):
            if free(x, y):
                found = (x, y)
                break
        if found:
            break
    if found is None:
        return []
    plot = Plot(entity.id, w, h, False, x=found[0], y=found[1])
    dx, dy = spot[0] - plot.cx, spot[1] - plot.cy
    plot.door_side = ("e" if dx > 0 else "w") if abs(dx) >= abs(dy) else ("s" if dy > 0 else "n")
    terrain, _, regions, doors = _paint({entity.id: plot})
    tiles = [fx.Tile(x=x, y=y, terrain=t) for (x, y), t in sorted(terrain.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    x0, y0, x1, y1 = plot.rect()
    effects: list = [fx.CreateEntity(entity=entity), fx.SetTiles(tiles=tiles, regions=[Region(place=entity.id, x0=x0, y0=y0, x1=x1, y1=y1)])]
    working = state.model_copy(deep=True)
    for e in effects:
        apply_effect(working, e)
    for a, b in sorted(grid.adjacency(working)):
        if entity.id in (a, b) and edge_key(a, b) not in state.edges:
            other = b if a == entity.id else a
            ca = (plot.cx, plot.cy)
            cb = _centre_of(working, other)
            effects.append(fx.SetEdge(a=a, b=b, edge=PlaceEdge(travel_minutes=max(1, round(math.dist(ca, cb) / grid.TILES_PER_MINUTE)))))
    return effects
