"""Plain-text views of world state for prompts.

Everything here describes what is locally true. Callers decide who is allowed
to see it: the Game Master gets ground truth, agents get it filtered.
"""

from tinyworld.core.ids import EntityId
from tinyworld.core.state import Entity, WorldState


def name_of(state: WorldState, entity_id: str | None) -> str:
    if entity_id is None:
        return "nowhere"
    entity = state.entities.get(entity_id)
    return entity.name if entity else entity_id


def inventory_text(state: WorldState, holder: Entity) -> str:
    if not holder.inventory:
        return "nothing"
    return ", ".join(
        f"{quantity} {name_of(state, item)} [{item}]"
        for item, quantity in sorted(holder.inventory.items())
    )


def local_ids(state: WorldState, agent_id: EntityId) -> set[str]:
    """Entities an action taken by ``agent_id`` could plausibly touch."""
    agent = state.entities.get(agent_id)
    if agent is None or agent.location is None:
        return {agent_id}
    here = agent.location
    ids = {agent_id, here}
    for entity in state.entities.values():
        if entity.location == here:
            ids.add(entity.id)
    for holder_id in list(ids):
        ids.update(state.entities[holder_id].inventory)
    for process in state.processes.values():
        if process.location == here or process.owner == agent_id:
            ids.add(process.id)
    return ids


def describe_place(state: WorldState, place_id: EntityId, *, viewer: str | None = None) -> str:
    place = state.entities[place_id]
    lines = [f"Place: {place.name} [{place.id}]"]
    if place.attrs.get("description"):
        lines.append(f"  {place.attrs['description']}")

    people = [p for p in state.people_at(place_id) if p.id != viewer]
    lines.append(
        "People here: "
        + (", ".join(f"{p.name} [{p.id}]" for p in people) if people else "nobody else")
    )
    if viewer is not None and state.grid:
        from tinyworld.world import grid, walking

        me = state.entities[viewer]
        where = walking.where_is(state, me)
        if where:
            lines.append("  " + where)
        in_view = [(o, d) for o, d in grid.nearby(state, me) if o.location != place_id]
        if in_view:
            lines.append(
                "In view: " + ", ".join(
                    f"{o.name} [{o.id}] ({d} tiles away, at {name_of(state, o.location)})" for o, d in in_view[:6]
                )
                + f". You can speak to anyone within {grid.TALK_RANGE} tiles."
            )
    bodies = [p for p in state.people_at(place_id, alive=False) if not p.alive]
    if bodies:
        lines.append("Dead here: " + ", ".join(f"{p.name} [{p.id}]" for p in bodies))

    things = state.things_at(place_id)
    if things:
        lines.append("Things here: " + ", ".join(f"{t.name} [{t.id}]" for t in things))
    lines.append(f"Stored here: {inventory_text(state, place)}")

    exits = [
        f"{name_of(state, other)} [{other}] ({edge.travel_minutes} min)"
        for other, edge in sorted(state.neighbors(place_id).items())
    ]
    lines.append("Exits: " + (", ".join(exits) if exits else "none"))

    processes = [
        p for p in state.processes.values()
        if p.status == "active" and p.location == place_id
    ]
    for process in processes:
        lines.append(
            f"Ongoing here: {process.name} [{process.id}], "
            f"{round(process.progress * 100)}% done"
        )
    return "\n".join(lines)


def describe_person(state: WorldState, person_id: EntityId) -> str:
    person = state.entities[person_id]
    parts = [f"{person.name} [{person.id}]"]
    for key in ("occupation", "age", "status", "health"):
        if key in person.attrs:
            parts.append(f"{key}: {person.attrs[key]}")
    if not person.alive:
        parts.append("dead")
    parts.append(f"carrying: {inventory_text(state, person)}")
    return "; ".join(parts)


def describe_facts(state: WorldState, *, public_only: bool = True, limit: int = 12) -> str:
    facts = [f for f in state.active_facts() if f.public or not public_only]
    if not facts:
        return "none"
    return "\n".join(f"- {fact.text}" for fact in facts[-limit:])


def describe_relation(state: WorldState, source: EntityId, dest: EntityId) -> str:
    relation = state.relation(source, dest)
    if relation is None:
        return "no particular relation"
    return f"{relation.kind} ({relation.value:+d})"
