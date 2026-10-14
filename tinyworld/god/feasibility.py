"""Checking god commands against the world before anything is changed."""

import re
from datetime import datetime
from typing import Literal

from pydantic import Field

from tinyworld.core.ids import make_id, slugify
from tinyworld.core.registry import REGISTRY, AttrRegistry
from tinyworld.core.state import Model, WorldState
from tinyworld.god.parser import GodCommand, resolve

Verdict = Literal["apply", "apply_adjusted", "needs_fork", "reject"]
_RULE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_RANK = {"apply": 0, "apply_adjusted": 1, "needs_fork": 2, "reject": 3}


class Judgement(Model):
    verdict: Verdict
    explanation: str
    # The command as it will actually be carried out.
    command: GodCommand
    when: datetime | None = None
    notes: list[str] = Field(default_factory=list)


def parse_when(text: str) -> datetime | None:
    if not text.strip():
        return None
    moment = datetime.fromisoformat(text.strip())
    # A bare date means the start of that working day.
    return moment.replace(hour=8) if len(text.strip()) <= 10 else moment


def hub_place(state: WorldState) -> str | None:
    """The best-connected place, used when a location has to be assumed."""
    places = [e.id for e in state.entities.values() if e.kind == "place"]
    if not places:
        return None
    return max(sorted(places), key=lambda place: len(state.neighbors(place)))


def _not_yet(state: WorldState, text: str) -> str | None:
    """A technology this world lists as not yet existing that ``text`` mentions."""
    lowered = text.lower()
    for item in state.rules.get("tech.not_yet") or []:
        if isinstance(item, str) and item.lower() in lowered:
            return item
    return None


def judge(
    state: WorldState,
    command: GodCommand,
    *,
    registry: AttrRegistry = REGISTRY,
    pending_places: set[str] | None = None,
) -> Judgement:
    """Decide whether one command can be applied, and in what adjusted form.

    ``pending_places`` are ids that earlier commands in the same request will
    have created by the time this one runs.
    """
    pending_places = pending_places or set()
    notes: list[str] = []
    adjusted = False

    def reject(why: str) -> Judgement:
        return Judgement(verdict="reject", explanation=why, command=command)

    try:
        when = parse_when(command.when)
    except ValueError:
        return reject(f"The time {command.when!r} could not be read.")
    if when is not None and when < state.sim_time:
        return Judgement(
            verdict="needs_fork",
            explanation=(
                f"That lies in the past ({when:%d %B %Y}). History is not rewritten in "
                "place: confirm to branch the timeline at that moment and apply it there."
            ),
            command=command,
            when=when,
        )
    if when is not None and when == state.sim_time:
        when = None

    op = command.op

    if op == "spawn":
        if command.kind is None or not command.name.strip():
            return reject("A new thing needs a kind and a name.")
        try:
            new_id = make_id(command.kind, command.name)
        except ValueError:
            return reject(f"{command.name!r} cannot be used as a name.")
        if new_id in state.entities:
            return reject(f"{state.entities[new_id].name} already exists.")
        location = ""
        if command.kind in ("person", "item", "place"):
            found = resolve(state, command.location, "place")
            if found is None and command.location:
                try:
                    candidate = make_id("place", command.location)
                except ValueError:
                    candidate = ""
                if candidate in pending_places:
                    found = candidate
            if found is None and command.kind == "person":
                # People need somewhere to be. A missing home becomes a new house.
                house = f"{command.name.split()[-1]} House"
                location = f"new:{house}"
                adjusted = True
                notes.append(
                    f"No existing place matched {command.location or 'the request'!r}, "
                    f"so a home was created: {house}."
                )
            elif found is None and command.kind == "item":
                found = hub_place(state)
                if found is None:
                    return reject("There is nowhere to put it.")
                adjusted = True
                notes.append(f"Placed at {state.entities[found].name}.")
                location = found
            elif found is None:
                found = hub_place(state)
                location = found or ""
                if found:
                    notes.append(f"Connected to {state.entities[found].name}.")
            else:
                location = found
        for key, value in command.attrs.items():
            reason = registry.check(command.kind, key, value)
            if reason:
                return reject(reason + f". Allowed: {', '.join(registry.keys(command.kind))}.")
        anachronism = _not_yet(state, f"{command.name} {command.description}")
        if anachronism:
            notes.append(
                f"Note: {anachronism!r} does not exist yet in this world. It is created "
                "because you asked; people here will treat it as unheard of."
            )
        command = command.model_copy(update={"location": location})

    elif op in ("remove", "modify", "move"):
        target = resolve(state, command.target)
        if target is None:
            return reject(f"Nothing here is called {command.target!r}.")
        entity = state.entities[target]
        update: dict = {"target": target}
        if op == "remove":
            mode = command.attrs.get("mode") or ("kill" if entity.kind == "person" else "erase")
            if mode not in ("kill", "erase"):
                return reject("Removal mode must be 'kill' or 'erase'.")
            if mode == "kill":
                if entity.kind != "person":
                    return reject(f"{entity.name} is not a person and cannot die.")
                if not entity.alive:
                    return reject(f"{entity.name} is already dead.")
            elif entity.kind == "place" and any(
                e.location == target for e in state.entities.values()
            ):
                return reject(f"{entity.name} is not empty.")
            update["attrs"] = {**command.attrs, "mode": mode}
        elif op == "move":
            if entity.kind == "place":
                return reject("Places cannot be moved.")
            destination = resolve(state, command.location, "place")
            if destination is None:
                return reject(f"There is no place called {command.location!r}.")
            if entity.location == destination:
                return reject(f"{entity.name} is already there.")
            update["location"] = destination
        else:
            if command.item:
                item = resolve(state, command.item)
                if item is None or state.entities[item].kind not in ("item", "resource"):
                    return reject(f"{command.item!r} is not something that can be held.")
                if command.quantity == 0:
                    return reject("A quantity is needed.")
                if entity.inventory.get(item, 0) + command.quantity < 0:
                    return reject(f"{entity.name} does not have that many.")
                update["item"] = item
            elif command.key:
                reason = registry.check(entity.kind, command.key, command.value)
                if reason:
                    return reject(reason + f". Allowed: {', '.join(registry.keys(entity.kind))}.")
            else:
                return reject("Say which attribute to change, or what to give or take.")
        command = command.model_copy(update=update)

    elif op in ("trigger_event", "change_environment"):
        if not command.description.strip():
            return reject("Describe what happens.")
        if command.location:
            location = resolve(state, command.location, "place")
            if location is None:
                return reject(f"There is no place called {command.location!r}.")
            command = command.model_copy(update={"location": location})

    elif op == "change_rule":
        if not command.key.strip():
            return reject("Name the rule to change.")
        if not _RULE_KEY.fullmatch(command.key) or "__" in command.key:
            return reject(f"{command.key!r} is not a usable rule name.")

    elif op == "advance_time":
        if command.minutes <= 0:
            return reject("Time can only move forward.")
        if when is not None:
            return reject("A time skip cannot itself be scheduled.")

    elif op == "start_process":
        owner = resolve(state, command.target)
        if owner is None:
            return reject("An undertaking needs someone existing to own it.")
        if not command.name.strip():
            return reject("An undertaking needs a name.")
        update = {"target": owner}
        if command.location:
            location = resolve(state, command.location, "place")
            if location is None:
                return reject(f"There is no place called {command.location!r}.")
            update["location"] = location
        try:
            process_id = "process:" + slugify(command.name)
        except ValueError:
            return reject(f"{command.name!r} cannot be used as a name.")
        if process_id in state.processes:
            return reject(f"{command.name} is already under way.")
        anachronism = _not_yet(state, f"{command.name} {command.description}")
        if anachronism:
            notes.append(
                f"Note: {anachronism!r} does not exist yet here. The undertaking is "
                "started; whether it can succeed is up to the world."
            )
        command = command.model_copy(update=update)

    if when is not None:
        notes.append(f"Scheduled for {when:%d %B %Y, %H:%M}.")
    verdict: Verdict = "apply_adjusted" if adjusted else "apply"
    explanation = " ".join(notes) or "Feasible as asked."
    return Judgement(
        verdict=verdict, explanation=explanation, command=command, when=when, notes=notes
    )


def overall(judgements: list[Judgement]) -> Verdict:
    """The strictest verdict decides for the whole request."""
    if not judgements:
        return "reject"
    return max((j.verdict for j in judgements), key=_RANK.__getitem__)
