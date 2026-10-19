"""Laws: rules a group with authority asserts, which the Game Master applies.

A law is an ordinary fact (``fact:law_*``) made by the leader of a group that has
authority. It names who it covers, what it forbids or requires, and what follows
a breach. The rule layer does not resolve an action a law touches by itself: it
hands it to the Game Master with the law written into the case, so a law changes
an adjudication (an arrest, a fine, a look the other way) rather than blocking
the action by magic.

Kinds of law, all checked mechanically so the match is not a model's guess:

- ``ban``     a verb (and optionally an item or a place) is forbidden;
- ``curfew``  being outdoors between two hours is forbidden;
- ``tax``     a share of coin received as wages is owed to the group.
"""

from tinyworld.core import effects as fx
from tinyworld.core.events import Intent, Verb
from tinyworld.core.state import Entity, Fact, WorldState
from tinyworld.world import institutions

PREFIX = "fact:law_"
KINDS = ("ban", "curfew", "tax")


def authority(state: WorldState, group: str) -> bool:
    entity = state.entities.get(group)
    return bool(entity and entity.attrs.get("authority") is True) or bool(entity and isinstance(entity.attrs.get("influence"), int) and entity.attrs["influence"] >= 60)


def laws(state: WorldState) -> list[Fact]:
    return sorted(
        (f for f in state.active_facts() if f.id.startswith(PREFIX) and isinstance(f.value, dict)),
        key=lambda f: f.id,
    )


def decree(state: WorldState, person: Entity, args: dict, text: str) -> tuple[list, str] | str:
    """A leader with authority asserts a law."""
    group = str(args.get("group", ""))
    if not group:
        mine = [g for g in institutions.groups_of(state, person.id) if institutions.leader_of(state, g) == person.id]
        group = mine[0] if mine else ""
    if not group or institutions.leader_of(state, group) != person.id:
        return "only the leader of a group can decree a law"
    if not authority(state, group):
        return f"{state.entities[group].name} has no authority to make law"
    kind = args.get("kind", "ban")
    if kind not in KINDS:
        return f"a law is one of: {', '.join(KINDS)}"
    law = {"kind": kind, "group": group, "text": (text or "").strip()}
    if not law["text"]:
        return "a law needs its words"
    if kind == "ban":
        verb = str(args.get("verb", "")).lower()
        if verb not in {v.value for v in Verb}:
            return "a ban names an action"
        law["verb"] = verb
        for key in ("item", "place"):
            if args.get(key):
                if args[key] not in state.entities:
                    return f"no such {key}"
                law[key] = args[key]
    elif kind == "curfew":
        start, end = args.get("from", 22), args.get("to", 5)
        if not all(isinstance(n, int) and 0 <= n <= 23 for n in (start, end)):
            return "a curfew has hours from 0 to 23"
        law["from"], law["to"] = start, end
    else:
        rate = args.get("rate", 0.1)
        if not isinstance(rate, (int, float)) or not 0 < rate <= 0.5:
            return "a tax is a rate up to one half"
        law["rate"] = rate
    n = sum(1 for f in state.facts if f.startswith(PREFIX)) + 1
    fact = Fact(
        id=f"{PREFIX}{n}", text=f"Law of {state.entities[group].name}: {law['text']}",
        subject=group, predicate="law", value=law,
    )
    return [fx.AssertFact(fact=fact)], f"{person.name} decrees for {state.entities[group].name}: {law['text']}"


def repeal(state: WorldState, person: Entity, law_id: str) -> tuple[list, str] | str:
    fact = state.facts.get(law_id)
    if fact is None or not state.fact_holds(law_id) or not law_id.startswith(PREFIX):
        return "no such law"
    if institutions.leader_of(state, fact.value["group"]) != person.id:
        return "only the group's leader can repeal its law"
    return [fx.RetractFact(fact_id=law_id)], f"{person.name} repeals: {fact.value['text']}"


def covers(state: WorldState, law: Fact, person: Entity) -> bool:
    """A law binds everyone in the town unless it names its group's own members only."""
    return True


def touching(state: WorldState, intent: Intent) -> list[Fact]:
    """The laws an intended action runs up against."""
    person = state.entities.get(intent.agent)
    if person is None:
        return []
    found = []
    for fact in laws(state):
        law = fact.value
        if not covers(state, fact, person):
            continue
        if law["kind"] == "ban" and intent.verb.value == law.get("verb"):
            if law.get("item") and intent.args.get("item") != law["item"]:
                continue
            if law.get("place") and person.location != law["place"] and intent.target != law["place"]:
                continue
            found.append(fact)
        elif law["kind"] == "curfew":
            hour, start, end = state.sim_time.hour, law["from"], law["to"]
            late = hour >= start or hour < end if start > end else start <= hour < end
            place = state.entities.get(person.location) if person.location else None
            outdoors = place is not None and place.attrs.get("place_type") in ("street", "wild")
            if late and (outdoors or intent.verb is Verb.MOVE):
                found.append(fact)
    return found


def prompt_lines(state: WorldState, intent: Intent) -> list[str]:
    return [f"- {f.text}" for f in touching(state, intent)]


def tax_due(state: WorldState, person: str, amount: int) -> list[tuple[str, int]]:
    """(group, coin) owed from ``amount`` received, by each tax in force."""
    out = []
    for fact in laws(state):
        law = fact.value
        if law["kind"] == "tax" and amount > 0:
            due = int(amount * law["rate"])
            if due > 0 and person not in institutions.members(state, law["group"]):
                out.append((law["group"], due))
    return out
