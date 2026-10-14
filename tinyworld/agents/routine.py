"""A person's ordinary day, worked out by rules so most hours need no model.

A routine is not a plan the model made. It is what a person with a home and a
workplace does by default: sleep at night, get ready in the morning, work in
the day. Evenings are free time, and that is where choices are left to the
model. A salient event, or a step that cannot be carried out, hands control
back to the model.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from tinyworld.core.events import Intent, Verb
from tinyworld.core.state import Entity, WorldState

DEFAULT_DAY = {"wake": 6, "work_start": 8, "work_end": 17, "sleep": 22}
Kind = Literal["sleep", "morning", "work", "promise"]
PROMISE_BUFFER_MINUTES = 15


@dataclass(frozen=True)
class Block:
    kind: Kind
    place: str
    until: datetime

    def minutes_left(self, now: datetime) -> int:
        return max(1, int((self.until - now).total_seconds() // 60))


def day_hours(state: WorldState) -> dict[str, int]:
    """Hours of the day, from the world rules where they are set."""
    raw = state.rules.get("day")
    hours = dict(DEFAULT_DAY)
    if isinstance(raw, dict):
        for key in DEFAULT_DAY:
            value = raw.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 23:
                hours[key] = value
    return hours


def _place(state: WorldState, entity: Entity, key: str) -> str | None:
    value = entity.attrs.get(key)
    if isinstance(value, str) and value in state.entities and state.entities[value].kind == "place":
        return value
    return None


def _at(now: datetime, hour: int, days: int = 0) -> datetime:
    return (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


def promise_lead(state: WorldState, entity: Entity, commitment) -> int | None:
    """Minutes before ``commitment`` falls due that the person must set out.

    None when the promise cannot be kept at all: no way to get there.
    """
    place = commitment.place
    if place is None or entity.location is None:
        return None
    if entity.location == place:
        return PROMISE_BUFFER_MINUTES
    route = state.path(entity.location, place)
    if route is None:
        return None
    return route[1] + PROMISE_BUFFER_MINUTES


def _promise_block(state: WorldState, entity: Entity, now: datetime) -> Block | None:
    """A promise to be somewhere comes before sleep, work and everything else."""
    due = []
    for commitment in state.open_commitments(entity.id):
        if commitment.by != entity.id or commitment.kind != "meet":
            continue
        lead = promise_lead(state, entity, commitment)
        if lead is None or now < commitment.due - timedelta(minutes=lead):
            continue
        due.append(commitment)
    if not due:
        return None
    first = min(due, key=lambda c: (c.due, c.id))
    return Block("promise", first.place, first.due)


def current_block(state: WorldState, entity: Entity, now: datetime | None = None) -> Block | None:
    """What this person is expected to be doing now, or None in free time."""
    now = now or state.sim_time
    if entity.alive and entity.attrs.get("status") != "child":
        kept = _promise_block(state, entity, now)
        if kept is not None:
            return kept
    home = _place(state, entity, "home")
    if home is None or entity.attrs.get("status") == "child":
        return None
    hours = day_hours(state)
    hour = now.hour
    if hour >= hours["sleep"] or hour < hours["wake"]:
        days = 1 if hour >= hours["sleep"] else 0
        return Block("sleep", home, _at(now, hours["wake"], days))
    work = _place(state, entity, "workplace")
    if work is None:
        return None
    if hours["wake"] <= hour < hours["work_start"]:
        return Block("morning", home, _at(now, hours["work_start"]))
    if hours["work_start"] <= hour < hours["work_end"]:
        return Block("work", work, _at(now, hours["work_end"]))
    return None


def routine_intent(
    state: WorldState, entity: Entity, block: Block, limit: int = 60
) -> Intent | None:
    """The intent that carries out ``block``, or None when it cannot be done."""
    if entity.location != block.place:
        if state.path(entity.location, block.place) is None:
            return None
        target = state.entities[block.place]
        return Intent(
            agent=entity.id, verb=Verb.MOVE, target=block.place,
            text=f"head to {target.name} ({block.kind})",
        )
    minutes = min(block.minutes_left(state.sim_time), max(1, limit))
    if block.kind == "promise":
        return Intent(
            agent=entity.id, verb=Verb.WAIT, args={"minutes": minutes},
            text="wait to keep a promise",
        )
    if block.kind == "sleep":
        return Intent(
            agent=entity.id, verb=Verb.REST, args={"minutes": minutes, "sleep": True},
            text="sleep",
        )
    if block.kind == "morning":
        return Intent(
            agent=entity.id, verb=Verb.REST, args={"minutes": minutes},
            text="get ready for the day",
        )
    return Intent(
        agent=entity.id, verb=Verb.WORK, args={"shift": True, "minutes": minutes},
        text=f"work as {entity.attrs.get('occupation') or 'usual'}",
    )


def has_routine(state: WorldState, entity: Entity) -> bool:
    return _place(state, entity, "home") is not None


def hint(state: WorldState, entity: Entity, block: Block | None) -> str:
    """A line for the prompt when a person is called out of their routine."""
    if block is None:
        if not has_routine(state, entity):
            return ""
        return "It is free time: nothing is expected of you right now."
    where = state.entities[block.place].name
    what = {
        "sleep": f"sleeping at {where}",
        "morning": f"getting ready at {where}",
        "work": f"working at {where}",
        "promise": f"being at {where} to keep a promise",
    }[block.kind]
    return f"Your usual routine now: {what}, until {block.until:%H:%M}."
