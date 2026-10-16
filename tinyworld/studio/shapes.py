"""Section shapes for agents, and forgiving reading of what they write.

A small open-weight model writing a world section from a prose brief guesses
field names: ``type`` for ``kind``, ``connected_to: ["Aminabad"]`` for
``connects_to: [{"to": "Aminabad"}]``. A strict schema then rejects every
attempt with "extra inputs are not permitted" and the task fails.

Two things fix that. The agent is shown the exact shape of the section it is
writing (``shape``). And what it writes is normalised before validation
(``normalise``): known near-miss names are mapped to the real ones, a plain
string where an object is expected becomes that object's first text field,
and anything still unknown is dropped. Everything changed is reported back,
so the agent learns the real shape instead of being silently corrected.
"""

from typing import Any

from pydantic import BaseModel

# Names models reach for, and the field they mean. Applied only when the real
# field exists on the model and the wrong one does not.
SYNONYMS = {
    "type": "kind", "category": "kind", "role": "kind",
    "connected_to": "connects_to", "connections": "connects_to", "links": "connects_to",
    "neighbours": "connects_to", "neighbors": "connects_to", "adjacent": "connects_to",
    "desc": "description", "details": "description", "about": "description",
    "title": "name", "label": "name",
    "occupation_title": "occupation", "job": "occupation", "profession": "occupation",
    "lives_at": "home", "residence": "home", "house": "home",
    "wants": "goals", "aims_list": "aims", "objectives": "aims", "goal": "goals",
    "personality": "traits", "fear": "fears", "secret": "secrets",
    "minutes": "travel_minutes", "distance_minutes": "travel_minutes", "travel_time": "travel_minutes",
    "target": "to", "place": "to", "destination": "to",
    "amount": "quantity", "count": "quantity",
    "person": "to", "with": "to",
    "summary_text": "summary", "bio": "summary", "background": "summary",
}


def _resolve(schema: dict, defs: dict) -> dict:
    while "$ref" in schema:
        schema = defs[schema["$ref"].split("/")[-1]]
    if "anyOf" in schema:
        options = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if options:
            return _resolve(options[0], defs)
    return schema


def _render(schema: dict, defs: dict, depth: int) -> str:
    schema = _resolve(schema, defs)
    kind = schema.get("type")
    if kind == "object" and "properties" in schema:
        if depth > 6:
            return "{...}"
        parts = [f"{name}: {_render(sub, defs, depth + 1)}" for name, sub in schema["properties"].items()]
        return "{" + ", ".join(parts) + "}"
    if kind == "object":
        return "{text: number}" if schema.get("additionalProperties", {}).get("type") == "integer" else "{...}"
    if kind == "array":
        return "[" + _render(schema.get("items", {}), defs, depth + 1) + ", ...]"
    if "enum" in schema:
        return "|".join(str(v) for v in schema["enum"])
    if "const" in schema:
        return str(schema["const"])
    return {"string": "text", "integer": "number", "number": "number", "boolean": "true|false"}.get(kind, "value")


def shape(model: type[BaseModel]) -> str:
    """A compact picture of the JSON a section must be, for the agent's brief."""
    schema = model.model_json_schema()
    return _render(schema, schema.get("$defs", {}), 0)


def _first_text_field(model: type[BaseModel]) -> str | None:
    for name, field in model.model_fields.items():
        if field.annotation is str:
            return name
    return None


def _item_model(annotation) -> type[BaseModel] | None:
    args = getattr(annotation, "__args__", ())
    for arg in args:
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    return None


def normalise(model: type[BaseModel], data: Any, notes: list[str], path: str = "") -> Any:
    """``data`` reshaped towards ``model``; every change is appended to ``notes``."""
    if not isinstance(data, dict):
        return data
    fields = model.model_fields
    out: dict = {}
    for key, value in data.items():
        name = key
        if key not in fields:
            mapped = SYNONYMS.get(key.lower())
            if mapped in fields and mapped not in data:
                name = mapped
                notes.append(f"{path}{key} read as {mapped}")
            else:
                notes.append(f"{path}{key} is not a field here, ignored")
                continue
        field = fields[name]
        annotation = field.annotation
        origin = getattr(annotation, "__origin__", None)
        if origin is list:
            item = _item_model(annotation)
            if item is not None and isinstance(value, list):
                fixed = []
                for index, element in enumerate(value):
                    if isinstance(element, str):
                        text_field = _first_text_field(item)
                        if text_field:
                            notes.append(f"{path}{name}.{index} '{element[:30]}' read as {{{text_field}: ...}}")
                            element = {text_field: element}
                    fixed.append(normalise(item, element, notes, f"{path}{name}.{index}."))
                value = fixed
            elif item is None and isinstance(value, str):
                value = [value]
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            value = normalise(annotation, value, notes, f"{path}{name}.")
        elif annotation is str and isinstance(value, (list, dict)):
            value = "; ".join(str(v) for v in value) if isinstance(value, list) else str(value)
            notes.append(f"{path}{name} joined into text")
        out[name] = value
    return out


# What a section must at least contain to count as written. Schema validation
# alone accepts an empty object, and dropping unknown fields can produce one.
MINIMUM = {
    "geography": ("places", 2, "at least two places"),
    "figures": ("figures", 2, "at least two people"),
    "factions": ("factions", 1, "at least one faction"),
    "tensions": ("tensions", 1, "at least one tension"),
    "politics": ("institutions", 1, "at least one institution"),
    "economy": ("resources", 1, "at least one resource"),
    "technology": ("available", 1, "at least one thing in everyday use"),
    "culture": ("norms", 1, "at least one norm"),
}


def too_thin(section: str, content: dict) -> str | None:
    """Why ``content`` does not yet count as the section, or None if it does."""
    rule = MINIMUM.get(section)
    if rule is None:
        return None
    key, least, words = rule
    items = content.get(key) or []
    if len(items) < least:
        return f"{section} needs {words} in `{key}`"
    return None
