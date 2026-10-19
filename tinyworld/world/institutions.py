"""Institutions: groups residents found, join, split and dissolve.

A group is an ``org`` entity: members are people with a ``member`` relation to
it, one of them is its ``leader``, it has ``aims``, and, if it has authority, it
may decree laws (``world/laws.py``). Everything is expressed as ordinary
effects, so a founding or a break-up is in the log and replays.

Actions (all rule-resolved, with reasons when they cannot be done):

- ``found``:  name + aims; the founder becomes leader and first member
- ``join`` / ``leave``: target is the group
- ``split``:  a member who is not the leader walks out with others to a new group
- ``dissolve``: the leader ends the group; its members are released
"""

from tinyworld.core import effects as fx
from tinyworld.core.ids import make_id
from tinyworld.core.state import Entity, Fact, WorldState

MEMBER = "member"
MIN_TO_FOUND = 1


def groups(state: WorldState) -> list[Entity]:
    return sorted((e for e in state.entities.values() if e.kind in ("org", "faction")), key=lambda e: e.id)


def members(state: WorldState, group: str) -> list[str]:
    out = []
    for key, relation in state.relations.items():
        who, dest = key.split(">")
        if dest == group and relation.kind == MEMBER and relation.value > 0:
            person = state.entities.get(who)
            if person is not None and person.alive:
                out.append(who)
    return sorted(out)


def groups_of(state: WorldState, person: str) -> list[str]:
    out = []
    for g in groups(state):
        relation = state.relation(person, g.id)
        if relation is not None and relation.kind == MEMBER and relation.value > 0:
            out.append(g.id)
    return out


def leader_of(state: WorldState, group: str) -> str | None:
    leader = state.entities[group].attrs.get("leader") if group in state.entities else None
    return leader if isinstance(leader, str) and leader in state.entities else None


def _count(state: WorldState, group: str, delta: int = 0) -> int:
    return max(0, len(members(state, group)) + delta)


def found(state: WorldState, person: Entity, name: str, aims: list[str]) -> tuple[list, str] | str:
    name = (name or "").strip()
    if not name or len(name) > 60:
        return "a group needs a name"
    try:
        gid = make_id("org", name)
    except ValueError:
        return "that is not a usable name"
    if gid in state.entities:
        return f"{name} already exists"
    if not aims:
        return "a group needs an aim"
    effects = [
        fx.CreateEntity(entity=Entity(
            id=gid, kind="org", name=name,
            attrs={"aims": aims[:4], "leader": person.id, "members": 1, "description": f"Founded by {person.name}."},
        )),
        fx.SetRelation(source=person.id, dest=gid, kind=MEMBER, value=80, note="founder"),
    ]
    return effects, f"{person.name} founds {name}: {'; '.join(aims[:2])}."


def join(state: WorldState, person: Entity, group: str) -> tuple[list, str] | str:
    g = state.entities.get(group)
    if g is None or g.kind not in ("org", "faction"):
        return "that is not a group"
    if group in groups_of(state, person.id):
        return f"{person.name} already belongs to {g.name}"
    return [
        fx.SetRelation(source=person.id, dest=group, kind=MEMBER, value=40, note="joined"),
        fx.SetAttr(entity=group, key="members", value=_count(state, group, 1)),
    ], f"{person.name} joins {g.name}."


def leave(state: WorldState, person: Entity, group: str) -> tuple[list, str] | str:
    g = state.entities.get(group)
    if g is None or group not in groups_of(state, person.id):
        return "not a member of that group"
    effects: list = [
        fx.SetRelation(source=person.id, dest=group, kind=MEMBER, value=-10, note="left"),
        fx.SetAttr(entity=group, key="members", value=_count(state, group, -1)),
    ]
    narration = f"{person.name} leaves {g.name}."
    if leader_of(state, group) == person.id:
        rest = [m for m in members(state, group) if m != person.id]
        effects.append(fx.SetAttr(entity=group, key="leader", value=rest[0] if rest else None))
        narration += f" {state.entities[rest[0]].name} takes over." if rest else " Nobody leads it now."
    return effects, narration


def dissolve(state: WorldState, person: Entity, group: str) -> tuple[list, str] | str:
    g = state.entities.get(group)
    if g is None or g.kind not in ("org", "faction"):
        return "that is not a group"
    if leader_of(state, group) != person.id:
        return "only its leader can dissolve a group"
    effects: list = []
    for m in members(state, group):
        effects.append(fx.SetRelation(source=m, dest=group, kind=MEMBER, value=-10, note="dissolved"))
    effects.append(fx.AssertFact(fact=Fact(
        id=f"fact:dissolved_{group.split(':')[1]}", text=f"{g.name} was dissolved by {person.name}.",
        subject=group, predicate="dissolved", value=True,
    )))
    effects.append(fx.SetAttr(entity=group, key="members", value=0))
    effects.append(fx.SetAttr(entity=group, key="leader", value=None))
    return effects, f"{person.name} dissolves {g.name}."


def split(state: WorldState, person: Entity, group: str, name: str, aims: list[str], followers: list[str]) -> tuple[list, str] | str:
    g = state.entities.get(group)
    if g is None or group not in groups_of(state, person.id):
        return "not a member of that group"
    if leader_of(state, group) == person.id:
        return "a leader dissolves a group; only members split from it"
    made = found(state, person, name, aims or list(g.attrs.get("aims", []))[:1])
    if isinstance(made, str):
        return made
    effects, _ = made
    new_id = effects[0].entity.id
    mine = {m for m in members(state, group)}
    take = [f for f in followers if f in mine and f != person.id][:6]
    effects.append(fx.SetRelation(source=person.id, dest=group, kind=MEMBER, value=-20, note="split away"))
    for f in take:
        effects.append(fx.SetRelation(source=f, dest=group, kind=MEMBER, value=-10, note="followed a split"))
        effects.append(fx.SetRelation(source=f, dest=new_id, kind=MEMBER, value=40, note="followed"))
    effects.append(fx.SetAttr(entity=group, key="members", value=max(0, _count(state, group, -(1 + len(take))))))
    effects.append(fx.SetAttr(entity=new_id, key="members", value=1 + len(take)))
    return effects, f"{person.name} breaks with {g.name} and founds {name}, taking {len(take)} with them."
