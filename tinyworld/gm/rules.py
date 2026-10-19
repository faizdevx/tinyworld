"""Deterministic checks for intents.

The rule layer answers three ways: the intent is impossible, it is fully
resolved here, or it is physically possible and needs the adjudicator to
decide what happens. No LLM is involved in this module.
"""

from dataclasses import dataclass
from typing import Literal

from tinyworld.core import effects as fx
from tinyworld.core.events import Intent, Outcome, Verb
from tinyworld.core.state import Entity, WorldState
from tinyworld.gm.context import name_of
from tinyworld.gm.verbs import DEFAULT_MINUTES, NEEDS_REACH


@dataclass
class Verdict:
    status: Literal["resolved", "impossible", "adjudicate"]
    outcome: Outcome | None = None
    reason: str = ""
    # Effects the rules already settled (speech riding along with an action).
    preset: list | None = None


def _impossible(intent: Intent, reason: str) -> Verdict:
    return Verdict(
        "impossible",
        Outcome(intent=intent, status="impossible", reason=reason),
        reason,
    )


def _resolved(intent: Intent, effects: list, narration: str, minutes: int, loud=False) -> Verdict:
    return Verdict(
        "resolved",
        Outcome(
            intent=intent, status="success", effects=effects,
            narration=narration, minutes=minutes, loud=loud,
        ),
    )


def _int_arg(intent: Intent, key: str, default: int) -> int | None:
    value = intent.args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def within_reach(state: WorldState, agent: Entity, target_id: str) -> bool:
    """True when the target is the agent, here, held by the agent, or this place."""
    if target_id in (agent.id, agent.location) or target_id in agent.inventory:
        return True
    target = state.entities.get(target_id)
    return target is not None and target.location == agent.location


def utter_effect(state: WorldState, agent: Entity, intent: Intent) -> tuple[fx.Utter | None, str]:
    """Build the speech effect for an intent, or explain why it cannot be said."""
    utterance = intent.utterance
    if utterance is None:
        return None, "nothing to say"
    for addressee_id in utterance.addressees:
        addressee = state.entities.get(addressee_id)
        if addressee is None or addressee.kind != "person":
            return None, f"{addressee_id} is not a person"
        if not addressee.alive:
            return None, f"{addressee.name} is dead"
        if utterance.channel != "written" and addressee.location != agent.location:
            from tinyworld.world import grid

            if not (grid.has_grid(state) and grid.can_talk(state, agent, addressee)):
                return None, f"{addressee.name} is not here"
    return (
        fx.Utter(
            speaker=agent.id,
            text=utterance.text,
            addressees=list(utterance.addressees),
            channel=utterance.channel,
            message_type=utterance.message_type,
            claims=list(utterance.claims),
        ),
        "",
    )


def speech_narration(state: WorldState, agent: Entity, utter: fx.Utter) -> str:
    if utter.addressees:
        names = ", ".join(name_of(state, a) for a in utter.addressees)
        return f'{agent.name} says to {names}: "{utter.text}"'
    verb = "announces" if utter.channel == "public" else "says"
    return f'{agent.name} {verb}: "{utter.text}"'


def process_blockers(state: WorldState, agent: Entity, process) -> list[str]:
    """Everything that stops ``agent`` from advancing ``process`` right now."""
    blockers: list[str] = []
    location = process.location
    if location is not None and agent.location != location:
        blockers.append(f"the work is at {name_of(state, location)}")
    where = location or agent.location
    requirements = process.requirements
    for participant in requirements.participants:
        person = state.entities.get(participant)
        if person is None or not person.alive:
            blockers.append(f"{name_of(state, participant)} is gone")
        elif person.location != where:
            blockers.append(f"{person.name} is not present")
    present = len(state.people_at(where)) if where else 0
    if present < requirements.min_workers:
        blockers.append(f"needs {requirements.min_workers} people, {present} present")
    holders = [state.entities.get(h) for h in (where, agent.id, process.owner) if h]
    for item, quantity in requirements.items.items():
        available = sum(h.inventory.get(item, 0) for h in holders if h is not None)
        if available < quantity:
            blockers.append(f"needs {quantity} {name_of(state, item)}, has {available}")
    for fact_id in requirements.facts:
        if not state.fact_holds(fact_id):
            fact = state.facts.get(fact_id)
            blockers.append(f"requires: {fact.text if fact else fact_id}")
    return blockers


def wage_for(state: WorldState, minutes: int) -> tuple[str, int] | None:
    """(item, amount) paid for ``minutes`` of work, from the world's wage rule."""
    rule = state.rules.get("wage")
    if not isinstance(rule, dict):
        return None
    item, per_hour = rule.get("item"), rule.get("per_hour")
    if (
        not isinstance(item, str) or item not in state.entities
        or isinstance(per_hour, bool) or not isinstance(per_hour, (int, float))
        or per_hour <= 0
    ):
        return None
    return item, max(1, round(per_hour * minutes / 60))


def _shift(state: WorldState, agent: Entity, intent: Intent, preset: list) -> Verdict:
    """A stretch of ordinary paid work at the person's workplace."""
    workplace = agent.attrs.get("workplace")
    if not isinstance(workplace, str) or workplace not in state.entities:
        return _impossible(intent, f"{agent.name} has no workplace")
    if agent.location != workplace:
        return _impossible(intent, f"{agent.name} is not at {name_of(state, workplace)}")
    minutes = _int_arg(intent, "minutes", DEFAULT_MINUTES[Verb.WORK])
    if minutes is None:
        return _impossible(intent, "minutes must be a positive whole number")
    effects = list(preset)
    paid = wage_for(state, minutes)
    if paid is not None:
        effects.append(fx.ChangeQuantity(holder=agent.id, item=paid[0], delta=paid[1]))
    return _resolved(
        intent, effects,
        f"{agent.name} works at {name_of(state, workplace)}.",
        minutes,
    )


def check(state: WorldState, intent: Intent) -> Verdict:
    agent = state.entities.get(intent.agent)
    if agent is None or agent.kind != "person":
        return _impossible(intent, "no such person")
    if not agent.alive:
        return _impossible(intent, f"{agent.name} is dead")
    if agent.location is None:
        return _impossible(intent, f"{agent.name} is not anywhere")

    verb = intent.verb
    target_id = intent.target
    target = state.entities.get(target_id) if target_id else None

    if verb is Verb.MOVE:
        if target is None or target.kind != "place":
            return _impossible(intent, "that is not a place")
        from tinyworld.world import grid, walking

        if grid.has_grid(state) and grid.position_of(agent) is not None:
            if target.id == agent.location and walking.route_of(agent) != target.id:
                return _impossible(intent, f"already at {target.name}")
            walk = walking.step(state, agent, target.id, resume=bool(intent.args.get("continue")))
            if isinstance(walk, str):
                return _impossible(intent, walk)
            effects, narration, minutes = walk
            return _resolved(intent, effects, narration, minutes)
        if target.id == agent.location:
            return _impossible(intent, f"already at {target.name}")
        route = state.path(agent.location, target.id)
        if route is None:
            return _impossible(intent, f"there is no way to {target.name} from here")
        return _resolved(
            intent,
            [fx.MoveEntity(entity=agent.id, to=target.id)],
            f"{agent.name} goes from {name_of(state, agent.location)} to {target.name}.",
            route[1],
        )

    if verb is Verb.SPEAK:
        utter, reason = utter_effect(state, agent, intent)
        if utter is None:
            return _impossible(intent, reason)
        if utter.channel == "written":
            return Verdict("adjudicate", preset=[utter])
        return _resolved(
            intent,
            [utter],
            speech_narration(state, agent, utter),
            DEFAULT_MINUTES[Verb.SPEAK],
            loud=utter.channel in ("audible", "public"),
        )

    if verb in (Verb.WAIT, Verb.REST):
        minutes = _int_arg(intent, "minutes", DEFAULT_MINUTES[verb])
        if minutes is None:
            return _impossible(intent, "minutes must be a positive whole number")
        doing = "waits" if verb is Verb.WAIT else "rests"
        if verb is Verb.REST and intent.args.get("sleep") is True:
            doing = "sleeps"
        return _resolved(intent, [], f"{agent.name} {doing}.", minutes)

    if verb is Verb.EXPLORE:
        from tinyworld.world import grid, walking

        if not grid.has_grid(state):
            return _impossible(intent, "there is no map to explore")
        direction = str(intent.args.get("direction", "")).lower()
        walk = walking.explore(state, agent, direction)
        if isinstance(walk, str):
            return _impossible(intent, walk)
        effects, narration, minutes = walk
        return _resolved(intent, effects, narration, minutes)

    if verb is Verb.PETITION:
        from tinyworld.world import petitions

        filed = petitions.file(state, agent, intent.args, intent.text)
        if isinstance(filed, str):
            return _impossible(intent, filed)
        effects, narration = filed
        return _resolved(intent, effects, narration, DEFAULT_MINUTES[Verb.PETITION])

    # Speech can ride along with any other action.
    preset: list = []
    if intent.utterance is not None:
        utter, reason = utter_effect(state, agent, intent)
        if utter is None:
            return _impossible(intent, reason)
        preset.append(utter)

    if verb is Verb.GIVE:
        item = intent.args.get("item")
        quantity = _int_arg(intent, "quantity", 1)
        if not isinstance(item, str) or item not in state.entities:
            return _impossible(intent, "no such item")
        if quantity is None:
            return _impossible(intent, "quantity must be a positive whole number")
        if target is None or target.kind not in ("person", "place"):
            return _impossible(intent, "nobody to give it to")
        if target.id == agent.id:
            return _impossible(intent, "cannot give to oneself")
        if target.kind == "person" and not target.alive:
            return _impossible(intent, f"{target.name} is dead")
        if not within_reach(state, agent, target.id):
            return _impossible(intent, f"{target.name} is not here")
        if agent.inventory.get(item, 0) < quantity:
            return _impossible(intent, f"{agent.name} does not have {quantity} {name_of(state, item)}")
        effects = preset + [
            fx.TransferItem(item=item, quantity=quantity, source=agent.id, dest=target.id)
        ]
        action = "leaves" if target.kind == "place" else "gives"
        where = "at" if target.kind == "place" else "to"
        return _resolved(
            intent,
            effects,
            f"{agent.name} {action} {quantity} {name_of(state, item)} {where} {target.name}.",
            DEFAULT_MINUTES[Verb.GIVE],
        )

    if verb is Verb.TAKE:
        item = intent.args.get("item")
        quantity = _int_arg(intent, "quantity", 1)
        if not isinstance(item, str) or item not in state.entities:
            return _impossible(intent, "no such item")
        if quantity is None:
            return _impossible(intent, "quantity must be a positive whole number")
        holder = target or state.entities.get(agent.location)
        if holder is None or not within_reach(state, agent, holder.id):
            return _impossible(intent, "that is not within reach")
        if holder.id == agent.id:
            return _impossible(intent, "already holding it")
        if holder.inventory.get(item, 0) < quantity:
            return _impossible(intent, f"there is not {quantity} {name_of(state, item)} to take")
        owner = holder.attrs.get("owner") if holder.kind == "place" else None
        free = holder.kind == "place" and owner in (None, agent.id)
        if free:
            return _resolved(
                intent,
                preset + [fx.TransferItem(item=item, quantity=quantity, source=holder.id, dest=agent.id)],
                f"{agent.name} takes {quantity} {name_of(state, item)} from {holder.name}.",
                DEFAULT_MINUTES[Verb.TAKE],
            )
        # Taking from a person or from someone else's property is contested.
        return Verdict("adjudicate", preset=preset)

    if verb is Verb.START:
        from tinyworld.world import projects

        begun = projects.begin(state, agent, intent.args, intent.text)
        if isinstance(begun, str):
            return _impossible(intent, begun)
        effects, narration = begun
        return _resolved(intent, preset + effects, narration, projects.START_MINUTES)

    if verb is Verb.WORK and intent.args.get("shift") is True:
        return _shift(state, agent, intent, preset)

    if verb is Verb.WORK and target_id in state.processes:
        process = state.processes[target_id]
        if process.status != "active":
            return _impossible(intent, f"{process.name} is no longer under way")
        blockers = process_blockers(state, agent, process)
        if blockers:
            return _impossible(intent, "; ".join(blockers))
        minutes = _int_arg(intent, "minutes", DEFAULT_MINUTES[Verb.WORK])
        if minutes is None:
            return _impossible(intent, "minutes must be a positive whole number")
        from tinyworld.world import projects

        delta = min(
            1.0 - process.progress,
            minutes / process.work_minutes * projects.skill_factor(state, agent, process),
        )
        effects = preset + [fx.AdvanceProcess(process_id=process.id, delta=delta)]
        narration = f"{agent.name} works on {process.name}."
        if process.progress + delta >= 1.0 - 1e-9:
            effects.append(fx.EndProcess(process_id=process.id, status="completed"))
            effects += projects.completion_effects(state, process, agent)
            narration = f"{agent.name} completes {process.name}."
        return _resolved(intent, effects, narration, minutes)

    if target_id is not None and target is None and target_id not in state.processes:
        return _impossible(intent, f"there is no {target_id}")
    if target is not None and verb in NEEDS_REACH and not within_reach(state, agent, target.id):
        return _impossible(intent, f"{target.name} is not here")
    if verb is Verb.ATTACK:
        if target is None or target.kind != "person":
            return _impossible(intent, "nobody to attack")
        if not target.alive:
            return _impossible(intent, f"{target.name} is already dead")
        if target.id == agent.id:
            return _impossible(intent, "cannot attack oneself")

    return Verdict("adjudicate", preset=preset)
