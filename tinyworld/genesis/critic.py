"""Consistency review of a bible: mechanical checks plus an LLM critic."""

from datetime import date

from tinyworld.core.ids import slugify
from tinyworld.genesis.bible import Bible, Critique, Finding
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext

CRITIC_SYSTEM = """You review a world description before it is simulated. Find real \
problems only:

- contradiction: two statements that cannot both be true.
- anachronism: something that could not exist or be known in this period, given \
the stated divergence from history.
- unmotivated_change: a difference from real history that does not follow from \
the divergence point.
- gap: something the simulation needs that is missing or too vague to use.

For each finding name the section it belongs to (geography, politics, economy, \
technology, culture, factions, figures, tensions). Mark it blocking only if the \
world should not be simulated until it is fixed. Return no findings when the \
description holds together; do not invent problems."""


def _slug(name: str) -> str:
    try:
        return slugify(name)
    except ValueError:
        return ""


def _duplicates(names: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated = []
    for name in names:
        slug = _slug(name)
        if slug in seen:
            repeated.append(name)
        seen.add(slug)
    return repeated


def connected_components(places: list[str], links: list[tuple[str, str]]) -> list[set[str]]:
    neighbours: dict[str, set[str]] = {place: set() for place in places}
    for a, b in links:
        if a in neighbours and b in neighbours:
            neighbours[a].add(b)
            neighbours[b].add(a)
    remaining = set(places)
    components = []
    while remaining:
        frontier = [next(iter(sorted(remaining)))]
        component: set[str] = set()
        while frontier:
            node = frontier.pop()
            if node in component:
                continue
            component.add(node)
            frontier.extend(neighbours[node] - component)
        components.append(component)
        remaining -= component
    return components


def check(bible: Bible) -> list[Finding]:
    """Problems that can be found without a model. All are reliable."""
    findings: list[Finding] = []

    def add(kind, section, text, blocking=True):
        findings.append(
            Finding(kind=kind, section=section, text=text, blocking=blocking, source="check")
        )

    try:
        date.fromisoformat(bible.premise.start_date)
    except ValueError:
        add("gap", "premise", f"start_date {bible.premise.start_date!r} is not a date (YYYY-MM-DD)")

    places = bible.geography.places
    place_slugs = {_slug(p.name) for p in places}
    if len(places) < 2:
        add("gap", "geography", "at least two places are needed")
    for name in _duplicates([p.name for p in places]):
        add("contradiction", "geography", f"place {name!r} is defined twice")
    links = []
    for place in places:
        for link in place.connects_to:
            if _slug(link.to) not in place_slugs:
                add("contradiction", "geography", f"{place.name!r} connects to unknown place {link.to!r}")
            elif _slug(link.to) == _slug(place.name):
                add("contradiction", "geography", f"{place.name!r} connects to itself")
            else:
                links.append((_slug(place.name), _slug(link.to)))
    if len(places) >= 2 and len(connected_components(sorted(place_slugs), links)) > 1:
        add("gap", "geography", "the places do not form one connected map")

    figures = bible.figures.figures
    figure_slugs = {_slug(f.name) for f in figures}
    faction_slugs = {_slug(f.name) for f in bible.factions.factions}
    resource_slugs = {_slug(r.name) for r in bible.economy.resources}
    if not figures:
        add("gap", "figures", "no individual people are defined")
    for name in _duplicates([f.name for f in figures]):
        add("contradiction", "figures", f"person {name!r} is defined twice")
    for figure in figures:
        if _slug(figure.home) not in place_slugs:
            add("contradiction", "figures", f"{figure.name} lives at unknown place {figure.home!r}")
        if figure.location and _slug(figure.location) not in place_slugs:
            add("contradiction", "figures", f"{figure.name} starts at unknown place {figure.location!r}")
        if figure.faction and _slug(figure.faction) not in faction_slugs:
            add("contradiction", "figures", f"{figure.name} belongs to unknown faction {figure.faction!r}")
        for possession in figure.possessions:
            if _slug(possession.resource) not in resource_slugs:
                add("contradiction", "figures", f"{figure.name} holds undefined resource {possession.resource!r}")
        for relation in figure.relations:
            if _slug(relation.to) not in figure_slugs:
                add("gap", "figures", f"{figure.name} has a relation to unknown person {relation.to!r}", blocking=False)
        if not figure.goals:
            add("gap", "figures", f"{figure.name} has no goals", blocking=False)

    for name in _duplicates([r.name for r in bible.economy.resources]):
        add("contradiction", "economy", f"resource {name!r} is defined twice")
    for stock in bible.economy.stocks:
        if _slug(stock.resource) not in resource_slugs:
            add("contradiction", "economy", f"stock of undefined resource {stock.resource!r}")
        if _slug(stock.holder) not in place_slugs | figure_slugs:
            add("contradiction", "economy", f"stock held by unknown {stock.holder!r}")

    available = {_slug(item) for item in bible.technology.available}
    for item in bible.technology.not_yet:
        if _slug(item) in available:
            add("contradiction", "technology", f"{item!r} is listed as both available and not yet invented")

    for name in _duplicates([f.name for f in bible.factions.factions]):
        add("contradiction", "factions", f"faction {name!r} is defined twice")
    for faction in bible.factions.factions:
        if faction.leader and _slug(faction.leader) not in figure_slugs:
            add("gap", "factions", f"{faction.name} is led by {faction.leader!r}, who is not among the key figures", blocking=False)
    return findings


async def review(
    llm: StructuredLLM, bible: Bible, context: CallContext
) -> list[Finding]:
    """The LLM critic's findings. Empty when the call fails."""
    document = bible.model_dump_json(exclude={"critique", "digest"}, indent=None)
    reply = await llm.call(
        "critic",
        Critique,
        system=CRITIC_SYSTEM,
        user=f"World description (JSON):\n{document}",
        context=context,
        fallback=Critique(),
        max_tokens=3000,
    )
    return [
        finding.model_copy(update={"source": "critic"})
        for finding in reply.value.findings
    ]
