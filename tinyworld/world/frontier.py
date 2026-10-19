"""The edge of the known world.

Only generated chunks exist. A chunk next to an ungenerated one has a *frontier*
on that side. When someone walks to it, or simply sees across it, the ungenerated
chunk is *requested*, once. A request is an ordinary fact, so the log says who
raised it and when, and a replay never raises it again.

The request is answered by the creators (``studio/creators.py``), whose proposal
is checked and laid out by ``genesis.layout.extend``; the result is ordinary
events, so replay does not call the creators.
"""

from dataclasses import dataclass

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.state import CHUNK, Fact, WorldState
from tinyworld.world import grid

PREFIX = "fact:frontier_"
DIRECTIONS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
WORDS = {(0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east"}


def _enc(n: int) -> str:
    return str(n) if n >= 0 else f"m{-n}"


def fact_id(cx: int, cy: int) -> str:
    return f"{PREFIX}{_enc(cx)}_{_enc(cy)}"


def chunk_key(cx: int, cy: int) -> str:
    return f"{cx},{cy}"


def parse(key: str) -> tuple[int, int]:
    a, b = key.split(",")
    return int(a), int(b)


@dataclass
class Request:
    chunk: str
    by: str
    reason: str
    status: str  # requested | generated | refused
    places: list[str]

    @property
    def cx(self) -> int:
        return parse(self.chunk)[0]

    @property
    def cy(self) -> int:
        return parse(self.chunk)[1]


def requests(state: WorldState) -> list[Request]:
    out = []
    for fact in state.facts.values():
        if fact.id.startswith(PREFIX) and isinstance(fact.value, dict):
            v = fact.value
            out.append(Request(
                chunk=str(v.get("chunk", "")), by=str(v.get("by", "")), reason=str(v.get("reason", "")),
                status=str(v.get("status", "requested")), places=list(v.get("places", [])),
            ))
    return sorted(out, key=lambda r: r.chunk)


def pending(state: WorldState) -> list[Request]:
    return [r for r in requests(state) if r.status == "requested"]


def known(state: WorldState, cx: int, cy: int) -> bool:
    return chunk_key(cx, cy) in state.grid


def missing_neighbours(state: WorldState) -> dict[str, list[str]]:
    """Ungenerated chunks that touch generated ones: {chunk: [directions you reach it from]}."""
    out: dict[str, list[str]] = {}
    for key in state.grid:
        cx, cy = parse(key)
        for word, (dx, dy) in DIRECTIONS.items():
            if not known(state, cx + dx, cy + dy):
                out.setdefault(chunk_key(cx + dx, cy + dy), []).append(WORDS[(-dx, -dy)])
    return out


def edge_tiles(state: WorldState, direction: str) -> list[tuple[int, int]]:
    """Passable tiles on the outer edge of the known world, on one side."""
    dx, dy = DIRECTIONS[direction]
    tiles = []
    for key in state.grid:
        cx, cy = parse(key)
        if known(state, cx + dx, cy + dy):
            continue
        for i in range(CHUNK):
            if dx:
                x = cx * CHUNK + (CHUNK - 1 if dx > 0 else 0)
                y = cy * CHUNK + i
            else:
                x = cx * CHUNK + i
                y = cy * CHUNK + (CHUNK - 1 if dy > 0 else 0)
            if grid.passable(state, x, y):
                tiles.append((x, y))
    return sorted(tiles)


def nearest_edge(state: WorldState, start: tuple[int, int], direction: str) -> tuple[int, int] | None:
    tiles = edge_tiles(state, direction)
    if not tiles:
        return None
    return min(tiles, key=lambda t: (grid.distance(start, t), t))


def chunk_seen_from(state: WorldState, spot: tuple[int, int], radius: int = grid.SIGHT) -> list[str]:
    """Ungenerated chunks within sight of a tile."""
    x, y = spot
    seen = []
    for cx in range((x - radius) // CHUNK, (x + radius) // CHUNK + 1):
        for cy in range((y - radius) // CHUNK, (y + radius) // CHUNK + 1):
            if known(state, cx, cy):
                continue
            x0, y0 = cx * CHUNK, cy * CHUNK
            nearest = (min(max(x, x0), x0 + CHUNK - 1), min(max(y, y0), y0 + CHUNK - 1))
            if grid.distance(spot, nearest) <= radius:
                seen.append(chunk_key(cx, cy))
    return seen


def scan(state: WorldState) -> list[tuple[str, str]]:
    """(chunk, person) for each ungenerated chunk someone can now see that nobody has asked about."""
    asked = {r.chunk for r in requests(state)}
    found: dict[str, str] = {}
    for person in sorted(state.people(), key=lambda p: p.id):
        spot = grid.position_of(person)
        if spot is None:
            continue
        for key in chunk_seen_from(state, spot):
            if key not in asked and key not in found and _adjacent_to_known(state, key):
                found[key] = person.id
    return sorted(found.items())


def _adjacent_to_known(state: WorldState, key: str) -> bool:
    cx, cy = parse(key)
    return any(known(state, cx + dx, cy + dy) for dx, dy in DIRECTIONS.values())


def request_draft(state: WorldState, key: str, by: str, reason: str) -> EventDraft | None:
    """The fact that a chunk is wanted. None if it was already asked about or already exists."""
    cx, cy = parse(key)
    if known(state, cx, cy) or fact_id(cx, cy) in state.facts:
        return None
    who = state.entities.get(by)
    name = who.name if who else by
    toward = [w for w, (dx, dy) in DIRECTIONS.items() if known(state, cx - dx, cy - dy)]
    side = f" to the {toward[0]}" if toward else ""
    fact = Fact(
        id=fact_id(cx, cy), text=f"{name} can see unexplored ground{side}.", subject=by, predicate="frontier",
        public=False, value={"chunk": key, "by": by, "reason": reason, "status": "requested", "places": []},
    )
    return EventDraft(
        kind="system", actor="system", visibility="god_only", effects=[fx.AssertFact(fact=fact)],
        narration=f"Unexplored ground is seen at chunk {key}.",
    )


def settled_effect(state: WorldState, key: str, status: str, places: list[str]) -> fx.AssertFact:
    cx, cy = parse(key)
    old = state.facts[fact_id(cx, cy)]
    value = dict(old.value) | {"status": status, "places": places}
    return fx.AssertFact(fact=old.model_copy(update={"value": value, "valid_from": old.valid_from}))
