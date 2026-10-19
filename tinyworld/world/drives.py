"""Drives: what residents want badly enough to make trouble.

Each person carries six drives (money, safety, status, belonging, faith,
curiosity), each with a level and a set point from 0 to 100. The set point is
what their persona would be content with; the level is where they are now.
*Frustration* is how far, over the drives that matter most to them, they are
below where they want to be. It feeds salience (a frustrated person is not left
on routine), planning (the prompt tells them what weighs on them), and
petitions and quarrels.

Levels move by events, by rule: ``consequences`` reads the new events and says
which drives they touch. Levels also drift back toward the set point a little
each day. Everything is written as ``SetAttr`` effects, so it is part of the log.
"""

import hashlib
from datetime import timedelta

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import Event, EventDraft
from tinyworld.core.state import Entity, WorldState

DRIVES = ("money", "safety", "status", "belonging", "faith", "curiosity")
KEY = "drives"
# Words in a persona that raise a set point.
LEANINGS = {
    "money": ("rich", "wealth", "profit", "debt", "poor", "thrift", "trade", "merchant", "shop", "coin", "money", "ledger", "stock", "income"),
    "safety": ("fear", "afraid", "cautious", "careful", "hide", "danger", "secure", "protect", "guard", "anxious", "requisition"),
    "status": ("proud", "vain", "ambitious", "standing", "reputation", "respect", "power", "office", "rank", "mayor", "boss", "leader"),
    "belonging": ("family", "loyal", "friend", "community", "neighbour", "children", "together", "kin", "belong"),
    "faith": ("pious", "faith", "god", "prayer", "church", "priest", "devout", "religion", "temple"),
    "curiosity": ("curious", "restless", "learn", "study", "question", "explore", "scholar", "student", "inventor", "restless"),
}
DAILY_DRIFT = 0.1  # share of the gap to the set point closed per day


def _digest(*parts: str) -> int:
    return int.from_bytes(hashlib.sha1("|".join(parts).encode()).digest()[:4], "big")


def initial(entity: Entity) -> dict[str, list[int]]:
    """{drive: [level, set_point]} worked out from the persona, the same way every time."""
    persona = persona_of(entity)
    text = " ".join(
        (persona.traits + persona.values + persona.goals + persona.fears + [persona.summary]) if persona else []
    ).lower()
    out = {}
    for name in DRIVES:
        hits = sum(1 for word in LEANINGS[name] if word in text)
        setpoint = max(30, min(90, 50 + 12 * min(hits, 3)))
        # Most people start a little short of where they would like to be.
        shortfall = 4 + _digest(entity.id, name) % 22
        out[name] = [max(0, setpoint - shortfall), setpoint]
    return out


def of(entity: Entity) -> dict[str, list[int]]:
    raw = entity.attrs.get(KEY)
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, pair in raw.items():
        if name in DRIVES and isinstance(pair, list) and len(pair) == 2 and all(isinstance(n, int) for n in pair):
            out[name] = pair
    return out


def deficits(entity: Entity) -> dict[str, int]:
    """How far below its set point each drive is (zero when at or above it)."""
    return {name: max(0, setpoint - level) for name, (level, setpoint) in of(entity).items()}


def frustration(entity: Entity) -> float:
    """0 to 1: the two largest shortfalls, as a share of 50 points."""
    gaps = sorted(deficits(entity).values(), reverse=True)[:2]
    if not gaps:
        return 0.0
    return round(min(1.0, sum(gaps) / (2 * 50)), 3)


def worst(entity: Entity) -> str | None:
    gaps = deficits(entity)
    if not gaps:
        return None
    name, gap = max(gaps.items(), key=lambda kv: (kv[1], kv[0]))
    return name if gap > 0 else None


def lines_for(entity: Entity) -> list[str]:
    """What weighs on this person, for their prompt. Empty when nothing does."""
    gaps = [(n, g) for n, g in sorted(deficits(entity).items(), key=lambda kv: -kv[1]) if g >= 12]
    if not gaps:
        return []
    words = {
        "money": "you do not have enough money", "safety": "you do not feel safe",
        "status": "you are not given the standing you deserve", "belonging": "you feel alone or let down",
        "faith": "your faith is shaken", "curiosity": "you are bored and want something new",
    }
    lines = ["", "What weighs on you:"]
    lines += [f"- {words[n]} ({'badly' if g >= 30 else 'somewhat'})" for n, g in gaps[:3]]
    if frustration(entity) >= 0.5:
        lines.append("You are frustrated enough to press for what you want, quarrel, or ask the god for help.")
    return lines


def _bump(entity: Entity, changes: dict[str, int]) -> fx.SetAttr | None:
    current = of(entity)
    if not current:
        return None
    new = {k: list(v) for k, v in current.items()}
    for name, delta in changes.items():
        if name in new:
            new[name][0] = max(0, min(100, new[name][0] + delta))
    return fx.SetAttr(entity=entity.id, key=KEY, value=new) if new != current else None


MONEY_WORDS = ("coin", "mark", "rupee", "money", "cash", "currency", "wage", "florin", "denar", "penny", "pound", "franc")


def _is_money(state: WorldState, item: str) -> bool:
    wage = state.rules.get("wage")
    if isinstance(wage, dict) and wage.get("item") == item:
        return True
    return any(w in item for w in MONEY_WORDS)


def consequences(state: WorldState, events: list[Event]) -> list[fx.SetAttr]:
    """The drive changes that follow from these events, as effects. ``state`` is after them."""
    changes: dict[str, dict[str, int]] = {}

    def note(person: str, drive: str, delta: int) -> None:
        entity = state.entities.get(person)
        if entity is not None and entity.kind == "person" and entity.alive:
            changes.setdefault(person, {}).setdefault(drive, 0)
            changes[person][drive] += delta

    for event in events:
        for effect in event.effects:
            if isinstance(effect, fx.ChangeQuantity) and _is_money(state, effect.item):
                note(effect.holder, "money", max(-15, min(15, effect.delta * 2)))
            elif isinstance(effect, fx.TransferItem):
                if _is_money(state, effect.item):
                    note(effect.dest, "money", min(15, effect.quantity * 2))
                    note(effect.source, "money", -min(15, effect.quantity * 2))
                elif event.actor == effect.source:
                    note(effect.dest, "belonging", 3)
                    note(effect.source, "belonging", 1)
                else:
                    note(effect.source, "safety", -6)  # something was taken from them
            elif isinstance(effect, fx.Kill):
                for other in state.people():
                    relation = state.relation(other.id, effect.entity)
                    if relation is not None and relation.value > 30:
                        note(other.id, "belonging", -20)
                        note(other.id, "safety", -8)
                    elif other.location == (event.location or "") and other.id != effect.entity:
                        note(other.id, "safety", -10)
            elif isinstance(effect, fx.SetRelation) and effect.value < -20:
                note(effect.source, "belonging", -6)
                note(effect.dest, "safety", -3)
            elif isinstance(effect, fx.SetAttr) and effect.key == "health" and isinstance(effect.value, int) and effect.value < 60:
                note(effect.entity, "safety", -8)
            elif isinstance(effect, fx.ResolveCommitment):
                promise = state.commitments.get(effect.commitment_id)
                if promise is not None:
                    if effect.status == "kept":
                        note(promise.by, "status", 3)
                        note(promise.to, "belonging", 2)
                    elif effect.status == "broken":
                        note(promise.by, "status", -5)
                        note(promise.to, "belonging", -6)
            elif isinstance(effect, fx.LearnKnowledge):
                note(effect.person, "curiosity", 10)
            elif isinstance(effect, fx.EndProcess) and effect.status == "completed":
                process = state.processes.get(effect.process_id)
                if process is not None:
                    note(process.owner, "status", 8)
            elif isinstance(effect, fx.Utter):
                if effect.message_type == "threaten":
                    for who in effect.addressees:
                        note(who, "safety", -10)
                elif effect.message_type in ("tell", "answer") and effect.addressees:
                    for who in effect.addressees:
                        note(who, "belonging", 1)
                    note(effect.speaker, "belonging", 1)
            elif isinstance(effect, fx.SetAttr) and effect.key == "faith" and isinstance(effect.value, int):
                note(effect.entity, "faith", 0)
    out = []
    for person in sorted(changes):
        bump = _bump(state.entities[person], changes[person])
        if bump is not None:
            out.append(bump)
    return out


def drift(state: WorldState, minutes: int) -> list[fx.SetAttr]:
    """Levels move back toward the set point as time passes."""
    share = DAILY_DRIFT * minutes / 1440
    out = []
    for person in sorted(state.people(), key=lambda p: p.id):
        current = of(person)
        if not current:
            continue
        new = {}
        for name, (level, setpoint) in current.items():
            step = round((setpoint - level) * share)
            if step == 0 and level != setpoint and share > 0 and abs(setpoint - level) >= 10:
                step = 1 if setpoint > level else -1
            new[name] = [max(0, min(100, level + step)), setpoint]
        if new != current:
            out.append(fx.SetAttr(entity=person.id, key=KEY, value=new))
    return out


def cast_draft(state: WorldState) -> EventDraft | None:
    """Give drives to every resident who has a persona and none yet."""
    effects = [
        fx.SetAttr(entity=p.id, key=KEY, value=initial(p))
        for p in sorted(state.people(), key=lambda p: p.id)
        if persona_of(p) is not None and not of(p)
    ]
    if not effects:
        return None
    return EventDraft(
        kind="system", actor="system", visibility="god_only", effects=effects,
        narration="Residents take on their wants.",
    )


def at_odds(state: WorldState, a: Entity, b: Entity) -> bool:
    """Two people want what only one can have: the same drive badly short in both, and bad blood or rivalry."""
    shared = set(deficits(a)) & set(deficits(b))
    both_short = [n for n in shared if deficits(a)[n] >= 20 and deficits(b)[n] >= 20]
    relation = state.relation(a.id, b.id)
    cold = relation is not None and relation.value < -10
    return bool(both_short) and cold
