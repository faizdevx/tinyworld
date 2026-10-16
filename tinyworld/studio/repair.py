"""Mechanical repairs to a draft, made openly before the merge.

The checks find problems that are bookkeeping, not judgement: a person owns a
resource the economy never defined, a home that is not one of the places, a
link to a place that does not exist. A small model fixing these by rewriting a
whole section often makes them worse. Like a linter's autofix, these are
repaired by rule, and every repair is listed for the user to see in the merge.

What is not repaired here is left to the writers and the reviewer: anything
that needs a decision about the world.
"""

from tinyworld.core.ids import slugify


def _slug(text: str) -> str:
    try:
        return slugify(text)
    except ValueError:
        return ""


def _closest(name: str, options: list[str]) -> str | None:
    """The option that is the same name, or contains it, or is contained by it."""
    want = _slug(name)
    if not want or not options:
        return None
    for option in options:
        if _slug(option) == want:
            return option
    for option in options:
        slug = _slug(option)
        if slug and (want in slug or slug in want):
            return option
    # Last, a shared distinctive word: "the traders" is "Traders Association".
    words = {w for w in want.split("_") if len(w) > 3}
    for option in options:
        if words & {w for w in _slug(option).split("_") if len(w) > 3}:
            return option
    return None


def repair(draft: dict) -> tuple[dict, list[str]]:
    """A repaired copy of ``draft`` and a line per repair."""
    import copy

    out = copy.deepcopy(draft)
    notes: list[str] = []
    geography = out.get("geography") or {}
    places = [p for p in geography.get("places", []) if isinstance(p, dict) and p.get("name")]
    place_names = [p["name"] for p in places]

    # Links to places that do not exist go; a place left alone joins the first one.
    for place in places:
        kept = []
        for link in place.get("connects_to", []) or []:
            target = link.get("to") if isinstance(link, dict) else None
            match = _closest(target or "", place_names)
            if match and match != place["name"]:
                kept.append({**link, "to": match})
            else:
                notes.append(f"geography: dropped a link from {place['name']} to {target!r}")
        place["connects_to"] = kept
    if len(places) >= 2:
        linked = {p["name"] for p in places if p.get("connects_to")} | {
            link["to"] for p in places for link in p.get("connects_to", [])
        }
        for place in places[1:]:
            if place["name"] not in linked:
                place.setdefault("connects_to", []).append({"to": places[0]["name"], "travel_minutes": 10})
                notes.append(f"geography: connected {place['name']} to {places[0]['name']}")

    economy = out.get("economy")
    resources = (economy or {}).get("resources", []) if economy is not None else []
    resource_names = [r.get("name") for r in resources if isinstance(r, dict) and r.get("name")]

    def need_resource(name: str, why: str) -> str:
        match = _closest(name, resource_names)
        if match:
            return match
        if economy is not None:
            economy.setdefault("resources", []).append({"name": name, "unit": "unit"})
            resource_names.append(name)
            notes.append(f"economy: defined resource {name!r} ({why})")
        return name

    factions = [f.get("name") for f in (out.get("factions") or {}).get("factions", []) if f.get("name")]
    figures = (out.get("figures") or {}).get("figures", [])
    for person in figures:
        if not isinstance(person, dict):
            continue
        who = person.get("name", "someone")
        for field in ("home", "location"):
            value = person.get(field) or ""
            if not value or not place_names or value in place_names:
                continue
            match = _closest(value, place_names) or place_names[0]
            notes.append(f"figures: {who}'s {field} {value!r} is now {match!r}")
            person[field] = match
        if not person.get("home") and place_names:
            person["home"] = place_names[0]
            notes.append(f"figures: {who} had no home; now {place_names[0]!r}")
        faction = person.get("faction") or ""
        if faction and faction not in factions:
            match = _closest(faction, factions)
            person["faction"] = match or ""
            notes.append(f"figures: {who}'s faction {faction!r} is now {match or 'none'!r}")
        for item in person.get("possessions", []) or []:
            if isinstance(item, dict) and item.get("resource"):
                item["resource"] = need_resource(item["resource"], f"owned by {who}")
                item.setdefault("holder", who)

    if economy is not None:
        holders = place_names + [p.get("name") for p in figures if isinstance(p, dict)]
        stocks = []
        for stock in economy.get("stocks", []) or []:
            if not isinstance(stock, dict):
                continue
            holder = _closest(stock.get("holder", ""), holders)
            if holder is None:
                notes.append(f"economy: dropped a stock held by unknown {stock.get('holder')!r}")
                continue
            stock["holder"] = holder
            stock["resource"] = need_resource(stock.get("resource", "goods"), f"stocked at {holder}")
            stocks.append(stock)
        economy["stocks"] = stocks
    return out, notes
