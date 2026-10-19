"""A synthetic town of any size, for cost and scale checks.

Not a story: names are generated, jobs are a short list, and everyone has a home, a workplace
and a few goals, a fear, and the three edges. It exists so that "50 residents for a week" can be run
and priced without writing 50 people by hand.
"""

import hashlib
from datetime import datetime

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.session import WorldSession
from tinyworld.core.state import Entity, PlaceEdge
from tinyworld.core.store import Store

FIRST = ["Anna", "Bruno", "Clara", "Dmitri", "Edda", "Felix", "Greta", "Hans", "Irene", "Jakob", "Katya", "Lukas", "Marta", "Nils", "Olga", "Pavel", "Quirin", "Rita", "Stefan", "Tilda", "Ulrich", "Vera", "Walter", "Xenia", "Yuri", "Zora"]
LAST = ["Adler", "Bauer", "Crane", "Dorn", "Eberle", "Fink", "Graf", "Haas", "Ivers", "Jung", "Kolb", "Lenz", "Mohr", "Noll", "Opitz", "Pohl", "Quast", "Reiss", "Sauer", "Thal"]
JOBS = ["baker", "smith", "farmer", "teacher", "clerk", "carter", "weaver", "innkeeper", "miller", "tailor", "priest", "doctor"]
WANTS = ["pay off a debt", "see the harvest in", "win a better post", "marry well", "keep a secret safe", "get out of town", "build something lasting", "be respected"]
FEARS = ["a bad winter", "being found out", "losing the shop", "illness", "the tax man"]
OPINIONS = ["outsiders bring trouble", "work is the only honest thing", "the old ways were better", "the council cannot be trusted"]
GRUDGES = ["a neighbour who cheated them", "the miller, over a weight", "the clerk, over a fine", "a cousin, over land"]
RIVAL = ["wants the same plot as a neighbour", "wants the post another has", "wants the market stall by the well"]


def _h(*p) -> int:
    return int.from_bytes(hashlib.sha1("|".join(map(str, p)).encode()).digest()[:4], "big")


def build(residents: int = 50, *, store: Store | None = None, start: datetime | None = None) -> WorldSession:
    store = store or Store()
    start = start or datetime(1900, 5, 1, 8)
    world = store.create_world("A synthetic town", start)
    session = WorldSession(store, store.create_branch(world, "base", start_time=start))
    homes = max(3, residents // 3)
    shops = max(3, residents // 5)
    effects = [fx.CreateEntity(entity=Entity(id="resource:coin", kind="resource", name="coin", attrs={"unit": "coin"})),
               fx.CreateEntity(entity=Entity(id="resource:bread", kind="resource", name="bread", attrs={"unit": "loaf"}))]
    places = [("place:square", "Town Square", "square")]
    places += [(f"place:house_{i}", f"House {i}", "house") for i in range(homes)]
    places += [(f"place:shop_{i}", f"Workshop {i}", "workshop") for i in range(shops)]
    places += [("place:chapel", "The Chapel", "shrine")]
    for pid, name, kind in places:
        effects.append(fx.CreateEntity(entity=Entity(id=pid, kind="place", name=name, attrs={"place_type": kind, "description": name})))
    for pid, _, _ in places[1:]:
        effects.append(fx.SetEdge(a="place:square", b=pid, edge=PlaceEdge(travel_minutes=2 + _h(pid) % 6)))
    people = []
    for i in range(residents):
        seen = {e.entity.id for e in people}
        for shift in range(len(LAST)):
            name = f"{FIRST[i % len(FIRST)]} {LAST[(i // len(FIRST) + _h(i) + shift) % len(LAST)]}"
            pid = "person:" + name.lower().replace(" ", "_")
            if pid not in seen:
                break
        else:
            name = f"{FIRST[i % len(FIRST)]} {LAST[i % len(LAST)]} {i}"
            pid = "person:" + name.lower().replace(" ", "_")
        home = f"place:house_{i % homes}"
        work = f"place:shop_{_h(i, 'w') % shops}"
        persona = {
            "summary": f"{name}, a {JOBS[_h(i, 'j') % len(JOBS)]}.",
            "traits": [["steady", "proud", "wary", "warm", "restless"][_h(i, 't') % 5]],
            "values": [["family", "thrift", "faith", "standing"][_h(i, 'v') % 4]],
            "goals": [WANTS[_h(i, 'g') % len(WANTS)], WANTS[_h(i, 'h') % len(WANTS)]],
            "fears": [FEARS[_h(i, 'f') % len(FEARS)]],
            "opinion": OPINIONS[_h(i, 'o') % len(OPINIONS)], "grudge": GRUDGES[_h(i, 'r') % len(GRUDGES)],
            "rival_want": RIVAL[_h(i, 'x') % len(RIVAL)],
            "aptitudes": {"craft": 3 + _h(i, 'a') % 6},
            "speech_style": "plain",
            "knowledge": {"era": "a small town, 1900"},
        }
        people.append(fx.CreateEntity(entity=Entity(
            id=pid, kind="person", name=name, location=home,
            attrs={"age": 20 + _h(i, 'age') % 40, "tier": 0, "home": home, "workplace": work,
                   "occupation": JOBS[_h(i, 'j') % len(JOBS)], "persona": persona},
            inventory={"resource:coin": 5 + _h(i, 'c') % 20, "resource:bread": 2},
        )))
    effects += people
    effects.append(fx.SetRule(key="wage", value={"item": "resource:coin", "per_hour": 1}))
    session.commit([EventDraft(kind="system", actor="system", visibility="god_only", effects=effects, narration="A town is built.")])
    # A few relations so there is someone to like and someone not to.
    rel = []
    ids = [p.entity.id for p in people]
    for i, a in enumerate(ids):
        b = ids[(i * 7 + 3) % len(ids)]
        if a != b:
            rel.append(fx.SetRelation(source=a, dest=b, kind="acquaintance", value=(_h(a, b) % 120) - 60))
    session.commit([EventDraft(kind="system", actor="system", visibility="god_only", effects=rel, narration="People know one another.")])
    return session
