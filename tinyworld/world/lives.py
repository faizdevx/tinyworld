"""Lives across generations: courtship, marriage, birth, ageing out, death, inheritance.

Everything is rule-based and drawn from ``Entropy`` (so two runs differ and a
replay is exact), and written as ordinary effects. Kinship is data on the person
(``parents``), marriage a ``spouse`` relation, and an inheritance an event whose
cause is the death, so the cause graph runs from a grandchild's choice back to a
grandparent's.

Who can marry: two living adults, not already married, not close kin, who hold
each other in warm regard. Who can have a child: a married pair where the younger
partner is within childbearing years. No assumption is made about anyone's sex;
a child has two parents.
"""

from datetime import timedelta

from tinyworld.agents.persona import Persona, persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.ids import make_id
from tinyworld.core.state import Entity, Fact, WorldState
from tinyworld.sim import tiers

ADULT = 18
YEAR_MINUTES = 365 * 24 * 60
SPOUSE = "spouse"
FERTILE = (18, 44)


def age_of(state: WorldState, person: Entity) -> int | None:
    return tiers.age_of(person, state.sim_time)


def parents_of(person: Entity) -> list[str]:
    raw = person.attrs.get("parents")
    return [p for p in raw if isinstance(p, str)] if isinstance(raw, list) else []


def children_of(state: WorldState, person_id: str) -> list[Entity]:
    return sorted(
        (p for p in state.people(alive=False) if person_id in parents_of(p)), key=lambda p: (str(p.attrs.get("birth_date", "")), p.id)
    )


def spouse_of(state: WorldState, person_id: str) -> str | None:
    for key, rel in state.relations.items():
        a, b = key.split(">")
        if a == person_id and rel.kind == SPOUSE and rel.value > 0 and b in state.entities and state.entities[b].alive:
            return b
    return None


def ancestors(state: WorldState, person_id: str, depth: int = 3) -> set[str]:
    found: set[str] = set()
    frontier = {person_id}
    for _ in range(depth):
        nxt: set[str] = set()
        for pid in frontier:
            p = state.entities.get(pid)
            if p is not None:
                nxt |= set(parents_of(p))
        found |= nxt
        frontier = nxt
    return found


def kin(state: WorldState, a: str, b: str) -> bool:
    """Too close to marry: parent and child, siblings, or grandparent and grandchild."""
    if a == b:
        return True
    pa, pb = state.entities.get(a), state.entities.get(b)
    if pa is None or pb is None:
        return False
    return (
        a in ancestors(state, b, 2) or b in ancestors(state, a, 2)
        or bool(set(parents_of(pa)) & set(parents_of(pb)))
    )


# -- marriage -------------------------------------------------------------------


def eligible(state: WorldState, a: Entity, b: Entity) -> bool:
    if not (a.alive and b.alive) or spouse_of(state, a.id) or spouse_of(state, b.id) or kin(state, a.id, b.id):
        return False
    aa, ab = age_of(state, a), age_of(state, b)
    if aa is None or ab is None or aa < ADULT or ab < ADULT or abs(aa - ab) > 20:
        return False
    ra, rb = state.relation(a.id, b.id), state.relation(b.id, a.id)
    return bool(ra and rb and ra.value >= 50 and rb.value >= 50)


def marriage_draft(state: WorldState, a: Entity, b: Entity, causes: list[int] | None = None) -> EventDraft:
    return EventDraft(
        kind="system", actor="system", location=a.location, visibility="public",
        effects=[
            fx.SetRelation(source=a.id, dest=b.id, kind=SPOUSE, value=90, note="married"),
            fx.SetRelation(source=b.id, dest=a.id, kind=SPOUSE, value=90, note="married"),
            fx.SetAttr(entity=a.id, key="spouse", value=b.id),
            fx.SetAttr(entity=b.id, key="spouse", value=a.id),
        ],
        narration=f"{a.name} and {b.name} marry.", causes=causes or [],
    )


def marriages(state: WorldState, minutes: int, entropy, rate_per_year: float = 0.35) -> list[EventDraft]:
    """Couples who are close enough may marry; chance is drawn, so runs differ."""
    out, used = [], set()
    people = sorted((p for p in state.people() if p.location), key=lambda p: p.id)
    for i, a in enumerate(people):
        for b in people[i + 1:]:
            if a.id in used or b.id in used or not eligible(state, a, b):
                continue
            if entropy.chance("marry", min(0.95, rate_per_year * minutes / YEAR_MINUTES)):
                out.append(marriage_draft(state, a, b))
                used |= {a.id, b.id}
    return out


# -- birth ------------------------------------------------------------------------

FIRST_NAMES = ["Anselm", "Berta", "Cosima", "Dieter", "Elke", "Falk", "Gerda", "Hugo", "Ida", "Jonas", "Klara", "Lukas", "Mara", "Nils", "Olga", "Piet", "Rosa", "Sven", "Tilda", "Uwe"]


def inherit_aptitudes(a: Entity, b: Entity, entropy) -> dict[str, int]:
    pa, pb = persona_of(a), persona_of(b)
    keys = sorted(set(pa.aptitudes if pa else {}) | set(pb.aptitudes if pb else {}))
    out = {}
    for k in keys:
        mean = ((pa.aptitudes.get(k, 3) if pa else 3) + (pb.aptitudes.get(k, 3) if pb else 3)) / 2
        out[k] = max(0, min(10, round(mean) + entropy.randint("inherit.aptitude", -1, 1)))
    return out


def birth_draft(state: WorldState, a: Entity, b: Entity, entropy, causes: list[int] | None = None) -> EventDraft | None:
    taken = set(state.entities)
    surname = a.name.split()[-1] if a.name.split() else a.name
    for _ in range(12):
        first = entropy.choice("birth.name", FIRST_NAMES)
        name = f"{first} {surname}"
        try:
            pid = make_id("person", name)
        except ValueError:
            continue
        if pid not in taken:
            break
    else:
        return None
    pa, pb = persona_of(a), persona_of(b)
    traits = []
    for p in (pa, pb):
        if p and p.traits:
            traits.append(entropy.choice("inherit.trait", p.traits))
    persona = Persona(
        summary=f"{name}, a child of {a.name} and {b.name}.",
        traits=list(dict.fromkeys(traits)), values=list((pa.values if pa else [])[:1] + (pb.values if pb else [])[:1]),
        aptitudes=inherit_aptitudes(a, b, entropy),
        speech_style=(pa.speech_style if pa else ""),
    )
    when = state.sim_time
    child = Entity(
        id=pid, kind="person", name=name, location=a.location,
        attrs={
            "age": 0, "birth_date": when.date().isoformat(), "status": "child", "tier": 2,
            "parents": [a.id, b.id], "persona": persona.model_dump(),
            "inherited": {"aptitudes": persona.aptitudes, "from": [a.id, b.id]},
        },
    )
    effects: list = [fx.CreateEntity(entity=child)]
    for parent in (a, b):
        effects.append(fx.SetRelation(source=parent.id, dest=pid, kind="parent", value=95, note="child"))
        effects.append(fx.SetRelation(source=pid, dest=parent.id, kind="child", value=80, note="parent"))
    return EventDraft(
        kind="system", actor="system", location=a.location, visibility="public", effects=effects,
        narration=f"{name} is born to {a.name} and {b.name}.", causes=causes or [],
    )


def births(state: WorldState, minutes: int, entropy, rate_per_year: float = 0.22) -> list[EventDraft]:
    out, done = [], set()
    for a in sorted(state.people(), key=lambda p: p.id):
        b_id = spouse_of(state, a.id)
        if b_id is None or a.id in done or b_id in done:
            continue
        b = state.entities[b_id]
        ages = (age_of(state, a), age_of(state, b))
        if None in ages or min(ages) < FERTILE[0] or min(ages) > FERTILE[1]:
            continue
        young = len([c for c in children_of(state, a.id) if age_of(state, c) is not None and age_of(state, c) < 3])
        if young >= 2:
            continue
        if entropy.chance("birth", min(0.95, rate_per_year * minutes / YEAR_MINUTES)):
            draft = birth_draft(state, a, b, entropy)
            if draft is not None:
                out.append(draft)
                done |= {a.id, b.id}
    return out


# -- death and inheritance ------------------------------------------------------------


def yearly_hazard(age: int, health: int = 100) -> float:
    base = 0.0008 + (0.00003 * max(0, age - 35) ** 2 if age > 35 else 0.0)
    if age < 5:
        base += 0.01
    if health < 30:
        base *= 4
    elif health < 60:
        base *= 2
    return min(0.9, base)


def deaths(state: WorldState, minutes: int, entropy) -> list[EventDraft]:
    out = []
    for p in sorted(state.people(), key=lambda p: p.id):
        age = age_of(state, p)
        if age is None:
            continue
        health = p.attrs.get("health", 100)
        health = health if isinstance(health, int) and not isinstance(health, bool) else 100
        h = 1 - (1 - yearly_hazard(age, health)) ** (minutes / YEAR_MINUTES)
        if entropy.chance("death", h):
            cause = "old age" if age >= 65 else "illness" if health < 60 else "a sudden illness"
            out.append(death_draft(state, p, cause))
    return out


def death_draft(state: WorldState, person: Entity, cause: str, causes: list[int] | None = None) -> EventDraft:
    return EventDraft(
        kind="system", actor="system", location=person.location, visibility="public",
        effects=[fx.Kill(entity=person.id, cause=cause)],
        narration=f"{person.name} dies of {cause}.", causes=causes or [],
    )


def heir_of(state: WorldState, person: Entity) -> Entity | None:
    """The eldest living child, else the spouse, else the nearest living kin; None if there is none."""
    for child in children_of(state, person.id):
        if child.alive:
            return child
    spouse = spouse_of(state, person.id)
    if spouse:
        return state.entities[spouse]
    for parent in parents_of(person):
        p = state.entities.get(parent)
        if p is not None and p.alive:
            return p
    siblings = [
        o for o in state.people() if o.id != person.id and set(parents_of(o)) & set(parents_of(person))
    ]
    return sorted(siblings, key=lambda o: o.id)[0] if siblings else None


def inheritance_draft(state: WorldState, dead: Entity, cause_seq: int | None = None) -> EventDraft | None:
    """What the dead leave: property and goods go to the heir, and so do their debts."""
    heir = heir_of(state, dead)
    if heir is None or heir.id == dead.id:
        return None
    effects: list = []
    for item, qty in sorted(dead.inventory.items()):
        effects.append(fx.TransferItem(item=item, quantity=qty, source=dead.id, dest=heir.id))
    for place in sorted(state.entities.values(), key=lambda e: e.id):
        if place.kind == "place" and place.attrs.get("owner") == dead.id:
            effects.append(fx.SetAttr(entity=place.id, key="owner", value=heir.id))
    for key, rel in sorted(state.relations.items()):
        a, b = key.split(">")
        if rel.kind == "owes" and rel.value > 0 and a == dead.id and b != heir.id:
            effects.append(fx.SetRelation(source=heir.id, dest=b, kind="owes", value=rel.value, note=rel.note))
            effects.append(fx.SetRelation(source=dead.id, dest=b, kind="acquaintance", value=0, note=""))
    if not effects:
        return None
    return EventDraft(
        kind="system", actor="system", location=heir.location, visibility="public", effects=effects,
        narration=f"{heir.name} inherits from {dead.name}.", causes=[cause_seq] if cause_seq else [],
    )


# -- the family tree --------------------------------------------------------------------


def tree(state: WorldState, root: str, depth: int = 4) -> dict:
    person = state.entities[root]
    node = {
        "id": root, "name": person.name, "alive": person.alive, "born": person.attrs.get("birth_date"),
        "spouse": spouse_of(state, root), "children": [],
    }
    if depth > 0:
        node["children"] = [tree(state, c.id, depth - 1) for c in children_of(state, root)]
    return node


def generations(state: WorldState, root: str) -> int:
    """How many generations the line from ``root`` runs to, counting the root as one."""
    kids = children_of(state, root)
    return 1 + (max(generations(state, c.id) for c in kids) if kids else 0)
