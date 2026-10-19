"""Tracing an event back through what led to it."""

from tinyworld.core import effects as fx
from tinyworld.core.events import Event
from tinyworld.core.store import Store


def _process_ids(event: Event) -> set[str]:
    ids = set()
    for effect in event.effects:
        if isinstance(effect, fx.StartProcess):
            ids.add(effect.process.id)
        elif isinstance(effect, (fx.AdvanceProcess, fx.EndProcess)):
            ids.add(effect.process_id)
    return ids


def _created_ids(event: Event) -> set[str]:
    return {e.entity.id for e in event.effects if isinstance(e, fx.CreateEntity)}


def cause_graph(
    store: Store, branch_id: str, seq: int, *, depth: int = 5, limit: int = 60
) -> dict:
    """Events leading to ``seq``, as nodes and edges.

    An edge is one of: "prompted" (the actor had just learned of the earlier
    event), "undertaking" (earlier work on the same long-running effort), or
    "origin" (the event that brought the actor into the world).
    """
    events = {e.seq: e for e in store.events(branch_id, upto=seq)}
    if seq not in events:
        return {"root": seq, "nodes": [], "edges": []}

    by_process: dict[str, list[int]] = {}
    origin: dict[str, int] = {}
    for event in events.values():
        for process_id in _process_ids(event):
            by_process.setdefault(process_id, []).append(event.seq)
        for created in _created_ids(event):
            origin.setdefault(created, event.seq)

    edges: list[dict] = []
    seen = {seq}
    frontier = [seq]
    for _ in range(depth):
        following: list[int] = []
        for current in frontier:
            event = events[current]
            links: list[tuple[int, str]] = [
                (cause, "prompted") for cause in event.causes if cause in events
            ]
            for process_id in _process_ids(event):
                earlier = [s for s in by_process[process_id] if s < current]
                # The start, and the step just before this one.
                for linked in {earlier[0], earlier[-1]} if earlier else ():
                    links.append((linked, "undertaking"))
            born = origin.get(event.actor)
            # A person's first act traces to the event that made them: the god's hand, or a birth.
            if born is not None and born < current and (events[born].actor == "god" or events[born].causes):
                links.append((born, "origin"))
            for linked, why in links:
                edges.append({"from": linked, "to": current, "why": why})
                if linked not in seen and len(seen) < limit:
                    seen.add(linked)
                    following.append(linked)
        frontier = following
        if not frontier:
            break

    unique = {(e["from"], e["to"], e["why"]): e for e in edges if e["from"] in seen}
    return {
        "root": seq,
        "nodes": [
            {
                "seq": s,
                "sim_time": events[s].sim_time.isoformat(),
                "actor": events[s].actor,
                "kind": events[s].kind,
                "narration": events[s].narration,
            }
            for s in sorted(seen)
        ],
        "edges": list(unique.values()),
    }
