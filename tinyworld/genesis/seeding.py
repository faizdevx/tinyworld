"""Turning a bible into the events that create the world."""

import math
from datetime import datetime

from tinyworld.agents.persona import KnowledgeBoundary, Persona
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.ids import make_id, slugify
from tinyworld.core.state import Entity, Fact, PlaceEdge, WorldState
from tinyworld.genesis.bible import Bible, Finding
from tinyworld.genesis.critic import connected_components


def start_time(bible: Bible) -> datetime:
    return datetime.fromisoformat(bible.premise.start_date).replace(hour=8)


def _layout(order: list[str], links: list[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    """Rings around the first place by link distance. Only a starting layout."""
    if not order:
        return {}
    neighbours: dict[str, list[str]] = {place: [] for place in order}
    for a, b in links:
        neighbours[a].append(b)
        neighbours[b].append(a)
    depth = {order[0]: 0}
    queue = [order[0]]
    while queue:
        node = queue.pop(0)
        for other in neighbours[node]:
            if other not in depth:
                depth[other] = depth[node] + 1
                queue.append(other)
    rings: dict[int, list[str]] = {}
    for place in order:
        rings.setdefault(depth.get(place, 1), []).append(place)
    positions = {}
    for ring, members in rings.items():
        for index, place in enumerate(members):
            angle = 2 * math.pi * index / len(members) + ring * 0.6
            positions[place] = (
                round(math.cos(angle) * ring * 160),
                round(math.sin(angle) * ring * 160),
            )
    return positions


def _system(effects: list, narration: str) -> EventDraft:
    return EventDraft(
        kind="system", actor="system", effects=effects,
        narration=narration, visibility="god_only",
    )


def seed_drafts(bible: Bible) -> tuple[list[EventDraft], list[Finding]]:
    """Seed events for ``bible`` and notes on anything that had to be repaired."""
    notes: list[Finding] = []

    def note(section: str, text: str) -> None:
        notes.append(
            Finding(kind="gap", section=section, text=text, blocking=False, source="check")
        )

    # -- resources ----------------------------------------------------------
    resources: dict[str, str] = {}
    resource_effects = []
    for spec in bible.economy.resources:
        resource_id = make_id("resource", spec.name)
        if resource_id in resources.values():
            continue
        resources[slugify(spec.name)] = resource_id
        attrs = {"unit": spec.unit, "scarcity": spec.scarcity}
        if spec.description:
            attrs["description"] = spec.description
        resource_effects.append(
            fx.CreateEntity(entity=Entity(id=resource_id, kind="resource", name=spec.name, attrs=attrs))
        )

    def resource(name: str, section: str) -> str | None:
        slug = slugify(name)
        if slug not in resources:
            # A resource used but never defined is created rather than dropped.
            resources[slug] = make_id("resource", name)
            resource_effects.append(
                fx.CreateEntity(entity=Entity(id=resources[slug], kind="resource", name=name))
            )
            note(section, f"resource {name!r} was not defined; created with defaults")
        return resources[slug]

    # -- places -------------------------------------------------------------
    places: dict[str, str] = {}
    order: list[str] = []
    for spec in bible.geography.places:
        slug = slugify(spec.name)
        if slug not in places:
            places[slug] = make_id("place", spec.name)
            order.append(slug)
    links: list[tuple[str, str]] = []
    edges: dict[tuple[str, str], PlaceEdge] = {}
    for spec in bible.geography.places:
        a = slugify(spec.name)
        for link in spec.connects_to:
            b = slugify(link.to)
            if b not in places or a == b:
                note("geography", f"dropped link from {spec.name!r} to {link.to!r}")
                continue
            key = tuple(sorted((a, b)))
            if key not in edges:
                links.append(key)
                edges[key] = PlaceEdge(
                    travel_minutes=link.travel_minutes,
                    visible=link.visible,
                    audible=link.audible,
                )
    components = connected_components(order, links)
    if len(components) > 1:
        hub = order[0]
        for component in components:
            if hub in component:
                continue
            stray = sorted(component, key=order.index)[0]
            key = tuple(sorted((hub, stray)))
            links.append(key)
            edges[key] = PlaceEdge(travel_minutes=15)
            note("geography", f"connected isolated place {stray!r} to {hub!r}")
    positions = _layout(order, links)

    figure_slugs = {slugify(f.name): make_id("person", f.name) for f in bible.figures.figures}

    place_effects = []
    owners: list[fx.SetAttr] = []
    seen_places: set[str] = set()
    for spec in bible.geography.places:
        slug = slugify(spec.name)
        if slug in seen_places:
            continue
        seen_places.add(slug)
        x, y = positions.get(slug, (0, 0))
        attrs = {"place_type": spec.kind, "enclosed": spec.enclosed, "x": x, "y": y}
        if spec.description:
            attrs["description"] = spec.description
        if spec.district:
            attrs["district"] = spec.district
        place_effects.append(
            fx.CreateEntity(entity=Entity(id=places[slug], kind="place", name=spec.name, attrs=attrs))
        )
        if spec.owner and slugify(spec.owner) in figure_slugs:
            owners.append(
                fx.SetAttr(entity=places[slug], key="owner", value=figure_slugs[slugify(spec.owner)])
            )
    edge_effects = [
        fx.SetEdge(a=places[a], b=places[b], edge=edge) for (a, b), edge in edges.items()
    ]

    def place(name: str, who: str) -> str:
        slug = slugify(name) if name.strip() else ""
        if slug in places:
            return places[slug]
        note("figures", f"{who}: unknown place {name!r}; placed at {order[0]!r}")
        return places[order[0]]

    # -- organisations and factions ----------------------------------------
    group_effects = []
    factions: dict[str, str] = {}
    for spec in bible.factions.factions:
        faction_id = make_id("faction", spec.name)
        if faction_id in factions.values():
            continue
        factions[slugify(spec.name)] = faction_id
        attrs = {
            "faction_type": spec.kind, "aims": list(spec.aims),
            "members": spec.members, "influence": spec.influence, "morale": 50,
        }
        if spec.description:
            attrs["description"] = spec.description
        if spec.leader and slugify(spec.leader) in figure_slugs:
            attrs["leader"] = figure_slugs[slugify(spec.leader)]
        group_effects.append(
            fx.CreateEntity(entity=Entity(id=faction_id, kind="faction", name=spec.name, attrs=attrs))
        )
    seen_orgs: set[str] = set()
    for spec in bible.politics.institutions:
        org_id = make_id("org", spec.name)
        if org_id in seen_orgs:
            continue
        seen_orgs.add(org_id)
        attrs = {"org_type": spec.kind, "aims": list(spec.aims), "members": spec.members, "morale": 50}
        if spec.description:
            attrs["description"] = spec.description
        if spec.leader and slugify(spec.leader) in figure_slugs:
            attrs["leader"] = figure_slugs[slugify(spec.leader)]
        group_effects.append(
            fx.CreateEntity(entity=Entity(id=org_id, kind="org", name=spec.name, attrs=attrs))
        )

    # -- people -------------------------------------------------------------
    era = ", ".join(part for part in (bible.premise.place, bible.premise.period) if part)
    people_effects = []
    relation_effects = []
    seen_people: set[str] = set()
    for spec in bible.figures.figures:
        person_id = figure_slugs[slugify(spec.name)]
        if person_id in seen_people:
            continue
        seen_people.add(person_id)
        home = place(spec.home, spec.name)
        persona = Persona(
            summary=spec.summary,
            traits=spec.traits,
            values=spec.values,
            goals=spec.goals,
            fears=spec.fears,
            secrets=spec.secrets,
            aptitudes=spec.aptitudes,
            speech_style=spec.speech_style,
            knowledge=KnowledgeBoundary(
                era=era,
                education=spec.education,
                knows=spec.knows,
                does_not_know=spec.does_not_know
                or [f"anything that happens after {bible.premise.start_date}"],
            ),
        )
        attrs = {
            "occupation": spec.occupation, "age": spec.age, "home": home,
            "tier": 0, "persona": persona.model_dump(),
        }
        if spec.faction and slugify(spec.faction) in factions:
            attrs["faction"] = factions[slugify(spec.faction)]
        inventory: dict[str, int] = {}
        for possession in spec.possessions:
            item = resource(possession.resource, "figures")
            inventory[item] = inventory.get(item, 0) + possession.quantity
        people_effects.append(
            fx.CreateEntity(
                entity=Entity(
                    id=person_id, kind="person", name=spec.name,
                    location=place(spec.location, spec.name) if spec.location else home,
                    attrs=attrs, inventory=inventory,
                )
            )
        )
    for spec in bible.figures.figures:
        source = figure_slugs[slugify(spec.name)]
        for relation in spec.relations:
            dest = figure_slugs.get(slugify(relation.to))
            if dest is None or dest == source:
                continue
            relation_effects.append(
                fx.SetRelation(source=source, dest=dest, kind=relation.kind, value=relation.value)
            )

    # -- stocks -------------------------------------------------------------
    stock_effects = []
    for stock in bible.economy.stocks:
        holder = places.get(slugify(stock.holder)) or figure_slugs.get(slugify(stock.holder))
        if holder is None:
            note("economy", f"dropped stock held by unknown {stock.holder!r}")
            continue
        stock_effects.append(
            fx.ChangeQuantity(holder=holder, item=resource(stock.resource, "economy"), delta=stock.quantity)
        )

    # -- facts and rules ----------------------------------------------------
    fact_effects = []
    for index, law in enumerate(bible.politics.laws, 1):
        fact_effects.append(fx.AssertFact(fact=Fact(id=f"fact:law_{index}", text=law)))
    for index, text in enumerate(bible.tensions.starting_facts, 1):
        fact_effects.append(fx.AssertFact(fact=Fact(id=f"fact:start_{index}", text=text)))
    for index, tension in enumerate(bible.tensions.tensions, 1):
        text = tension.text + (f" At stake: {tension.stakes}" if tension.stakes else "")
        # Tensions are ground truth for the Game Master, not common knowledge.
        fact_effects.append(
            fx.AssertFact(fact=Fact(id=f"fact:tension_{index}", text=text, public=False))
        )
    rule_effects = [
        fx.SetRule(key="era", value=era),
        fx.SetRule(key="tech.available", value=list(bible.technology.available)),
        fx.SetRule(key="tech.not_yet", value=list(bible.technology.not_yet)),
        fx.SetRule(
            key="population",
            value=[group.model_dump() for group in bible.culture.population],
        ),
    ]

    stages = [
        (resource_effects, "Resources defined."),
        (place_effects, "Places created."),
        (edge_effects, "Places connected."),
        (group_effects, "Institutions and factions created."),
        (people_effects, "People created."),
        (owners, "Ownership recorded."),
        (relation_effects, "Relations set."),
        (stock_effects, "Stock placed."),
        (fact_effects, "Starting facts asserted."),
        (rule_effects, "World rules set."),
    ]
    return [_system(effects, text) for effects, text in stages if effects], notes


def check_world(state: WorldState) -> list[str]:
    """Structural problems in a seeded world. Empty means it is ready to run."""
    problems: list[str] = []
    place_ids = [e.id for e in state.entities.values() if e.kind == "place"]
    if not place_ids:
        return ["the world has no places"]
    links = [tuple(key.split("|")) for key in state.edges]
    if len(connected_components(place_ids, links)) > 1:
        problems.append("the map is not connected")
    for key in state.edges:
        for end in key.split("|"):
            if end not in state.entities:
                problems.append(f"edge refers to missing place {end}")
    for person in state.people(alive=False):
        if person.location not in state.entities:
            problems.append(f"{person.id} has no valid location")
        home = person.attrs.get("home")
        if home not in state.entities:
            problems.append(f"{person.id} has no valid home")
        faction = person.attrs.get("faction")
        if faction is not None and faction not in state.entities:
            problems.append(f"{person.id} belongs to missing faction {faction}")
        for item in person.inventory:
            if item not in state.entities:
                problems.append(f"{person.id} holds missing item {item}")
    for key in state.relations:
        for end in key.split(">"):
            if end not in state.entities:
                problems.append(f"relation refers to missing entity {end}")
    for entity in state.entities.values():
        for reference in ("owner", "leader"):
            target = entity.attrs.get(reference)
            if target is not None and target not in state.entities:
                problems.append(f"{entity.id} {reference} refers to missing {target}")
    return problems
