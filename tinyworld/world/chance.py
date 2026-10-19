"""Chance events, and the chaos dial that scales them.

The world rule ``chaos`` (0 to 1) sets how often fortune strikes and how hard.
At 0 nothing happens by chance; at 1 a bad week is common. Every draw comes
from ``Entropy``, so a replay meets the same fortune.

A chance event is a small, concrete change expressed in the closed vocabulary
of effects: a fire takes stock, a thief takes a coin, a fever lowers health, a
windfall adds goods. Who it hits is also drawn.
"""

from dataclasses import dataclass

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.state import Entity, WorldState

RULE = "chaos"
# At chaos 1.0, chance events per resident per simulated day.
DAILY_RATE = 0.3
KINDS = ("fever", "theft", "fire", "windfall", "accident", "quarrel", "rumour")


def level(state: WorldState) -> float:
    value = state.rules.get(RULE, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


@dataclass
class Fortune:
    kind: str
    draft: EventDraft


def _health(person: Entity) -> int:
    value = person.attrs.get("health", 100)
    return value if isinstance(value, int) and not isinstance(value, bool) else 100


def _holders(state: WorldState) -> list[Entity]:
    return sorted(
        (e for e in state.entities.values() if e.inventory and e.kind in ("person", "place")),
        key=lambda e: e.id,
    )


def roll(state: WorldState, minutes: int, entropy) -> Fortune | None:
    """At most one chance event for a stretch of ``minutes``. None when fortune is quiet."""
    chaos = level(state)
    if chaos <= 0:
        return None
    people = sorted((x for x in state.people() if x.location), key=lambda e: e.id)
    if not people:
        return None
    p = min(0.95, DAILY_RATE * chaos * len(people) * minutes / 1440)
    if not entropy.chance("chance.happens", p):
        return None
    kind = entropy.choice("chance.kind", KINDS)
    victim = entropy.choice("chance.who", people)
    # How hard it lands grows with the dial.
    size = 1 + int(entropy.draw("chance.size") * (1 + 3 * chaos))
    place = state.entities.get(victim.location)

    if kind == "fever":
        health = max(5, _health(victim) - 10 * size)
        return Fortune(kind, EventDraft(
            kind="system", actor="system", location=victim.location, visibility="public",
            effects=[fx.SetAttr(entity=victim.id, key="health", value=health),
                     fx.SetAttr(entity=victim.id, key="mood", value="feverish and frightened")],
            narration=f"{victim.name} comes down with a fever.",
        ))
    if kind == "theft" and victim.inventory:
        item = entropy.choice("chance.item", sorted(victim.inventory))
        lost = min(victim.inventory[item], size)
        return Fortune(kind, EventDraft(
            kind="system", actor="system", location=victim.location, visibility="public",
            effects=[fx.ChangeQuantity(holder=victim.id, item=item, delta=-lost),
                     fx.SetAttr(entity=victim.id, key="mood", value="angry at being robbed")],
            narration=f"Someone takes {lost} {state.entities[item].name} from {victim.name}.",
        ))
    if kind == "fire":
        stocked = [h for h in _holders(state) if h.kind == "place"]
        if stocked:
            site = entropy.choice("chance.site", stocked)
            item = entropy.choice("chance.item", sorted(site.inventory))
            lost = max(1, min(site.inventory[item], size * 2))
            return Fortune(kind, EventDraft(
                kind="system", actor="system", location=site.id, visibility="public", loud=True,
                effects=[fx.ChangeQuantity(holder=site.id, item=item, delta=-lost)],
                narration=f"Fire at {site.name}: {lost} {state.entities[item].name} burns.",
            ))
    if kind == "windfall":
        goods = sorted(e.id for e in state.entities.values() if e.kind in ("resource", "item"))
        if goods:
            item = entropy.choice("chance.item", goods)
            return Fortune(kind, EventDraft(
                kind="system", actor="system", location=victim.location, visibility="public",
                effects=[fx.ChangeQuantity(holder=victim.id, item=item, delta=size)],
                narration=f"{victim.name} comes into {size} {state.entities[item].name} by luck.",
            ))
    if kind == "accident":
        health = max(5, _health(victim) - 8 * size)
        return Fortune(kind, EventDraft(
            kind="system", actor="system", location=victim.location, visibility="public", loud=True,
            effects=[fx.SetAttr(entity=victim.id, key="health", value=health)],
            narration=f"{victim.name} is hurt in an accident"
            + (f" at {place.name}." if place else "."),
        ))
    if kind == "quarrel" and len(people) > 1:
        other = entropy.choice("chance.other", [p for p in people if p.id != victim.id])
        old = state.relation(victim.id, other.id)
        value = max(-100, (old.value if old else 0) - 15 * size)
        return Fortune(kind, EventDraft(
            kind="system", actor="system", location=victim.location, visibility="public", loud=True,
            effects=[fx.SetRelation(source=victim.id, dest=other.id, kind="grudge", value=value,
                                    note="a quarrel that came from nowhere")],
            narration=f"{victim.name} and {other.name} quarrel bitterly over something small.",
        ))
    if kind == "rumour":
        return Fortune(kind, EventDraft(
            kind="system", actor="system", location=victim.location, visibility="public",
            effects=[fx.SetAttr(entity=victim.id, key="mood", value="uneasy, having heard something")],
            narration=f"A rumour about {victim.name} starts to go round.",
        ))
    return None

