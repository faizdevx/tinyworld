"""Entity identifiers in the ``kind:slug`` form used throughout v2."""

import re

ENTITY_KINDS = ("person", "place", "item", "org", "faction", "resource")

_ID = re.compile(r"^(?P<kind>[a-z]+):(?P<slug>[a-z0-9][a-z0-9_]*)$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

EntityId = str
FactId = str
ProcessId = str


def slugify(name: str) -> str:
    slug = _SLUG_STRIP.sub("_", name.strip().lower()).strip("_")
    if not slug:
        raise ValueError(f"cannot build an id from {name!r}")
    return slug


def make_id(kind: str, name: str) -> EntityId:
    if kind not in ENTITY_KINDS:
        raise ValueError(f"unknown entity kind: {kind}")
    return f"{kind}:{slugify(name)}"


def parse_id(entity_id: str) -> tuple[str, str]:
    match = _ID.match(entity_id) if isinstance(entity_id, str) else None
    if match is None or match["kind"] not in ENTITY_KINDS:
        raise ValueError(f"invalid entity id: {entity_id!r}")
    return match["kind"], match["slug"]


def kind_of(entity_id: str) -> str:
    return parse_id(entity_id)[0]


def edge_key(a: EntityId, b: EntityId) -> str:
    """Key for an undirected edge between two places."""
    first, second = sorted((a, b))
    return f"{first}|{second}"


def relation_key(source: EntityId, dest: EntityId) -> str:
    """Key for a directed relation."""
    return f"{source}>{dest}"
