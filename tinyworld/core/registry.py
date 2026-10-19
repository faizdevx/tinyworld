"""Per-kind attribute schema. ``SetAttr`` and ``CreateEntity`` are checked against it."""

from pydantic import JsonValue

Number = (int, float)


def _is(value: JsonValue, types) -> bool:
    allowed = types if isinstance(types, tuple) else (types,)
    if isinstance(value, bool) and bool not in allowed:
        return False
    return isinstance(value, allowed)


DEFAULT_ATTRS: dict[str, dict[str, object]] = {
    "person": {
        "role": str,
        "occupation": str,
        "age": int,
        "birth_date": str,
        "health": int,
        "mood": str,
        "status": str,
        "description": str,
        "home": str,
        "workplace": str,
        "reputation": int,
        "skills": dict,
        "tier": int,
        "persona": dict,
        "faction": str,
        "knowledge": dict,
        "faith": int,
        "drives": dict,
        "x": int,
        "y": int,
        "last_petition": str,
    },
    "place": {
        "description": str,
        "place_type": str,
        "capacity": int,
        "enclosed": bool,
        "owner": str,
        "x": Number,
        "y": Number,
        "district": str,
        "population": int,
    },
    "item": {"description": str, "item_type": str, "owner": str, "condition": str},
    "org": {
        "description": str,
        "org_type": str,
        "aims": list,
        "leader": str,
        "members": int,
        "resources": int,
        "morale": int,
    },
    "faction": {
        "description": str,
        "faction_type": str,
        "aims": list,
        "leader": str,
        "members": int,
        "influence": int,
        "morale": int,
    },
    "resource": {"description": str, "unit": str, "scarcity": str},
}


class AttrRegistry:
    def __init__(self, attrs: dict[str, dict[str, object]] | None = None) -> None:
        source = attrs if attrs is not None else DEFAULT_ATTRS
        self._attrs = {kind: dict(keys) for kind, keys in source.items()}

    def register(self, kind: str, key: str, types) -> None:
        self._attrs.setdefault(kind, {})[key] = types

    def keys(self, kind: str) -> list[str]:
        return sorted(self._attrs.get(kind, {}))

    def check(self, kind: str, key: str, value: JsonValue) -> str | None:
        """Return a reason when the attribute is not allowed, else None."""
        allowed = self._attrs.get(kind, {})
        if key not in allowed:
            return f"attribute {key!r} is not allowed on {kind}"
        if value is not None and not _is(value, allowed[key]):
            return f"attribute {key!r} on {kind} has the wrong type"
        return None


REGISTRY = AttrRegistry()
