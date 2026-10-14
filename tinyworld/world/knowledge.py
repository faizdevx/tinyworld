"""Ideas and techniques a world has, who holds them, and what they build on.

The graph is small on purpose: tens of nodes, each with the nodes it needs.
It is kept in the world rules under ``knowledge`` so it is part of the event
log like everything else. What a person holds is a mapping from idea to level
in their ``knowledge`` attribute, changed only by the ``LearnKnowledge`` effect.

``common`` ideas are known by everyone from the start. ``undiscovered`` ones
exist in nobody's head until a project works them out.
"""

from typing import Literal

from pydantic import Field

from tinyworld.core.ids import slugify
from tinyworld.core.state import Entity, Model, WorldState

KEY = "knowledge"
Status = Literal["common", "known", "rare", "undiscovered"]
MAX_LEVEL = 3


class Idea(Model):
    label: str = Field(min_length=1)
    requires: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=2, ge=1, le=5)
    status: Status = "common"


def idea_id(label: str) -> str:
    return f"idea:{slugify(label)}"


def ideas(state: WorldState) -> dict[str, Idea]:
    raw = state.rules.get(KEY)
    found: dict[str, Idea] = {}
    if not isinstance(raw, dict):
        return found
    for key, value in raw.items():
        try:
            found[key] = Idea.model_validate(value)
        except ValueError:
            continue
    return found


def graph_value(graph: dict[str, Idea]) -> dict:
    return {key: idea.model_dump() for key, idea in graph.items()}


def held(person: Entity) -> dict[str, int]:
    raw = person.attrs.get(KEY)
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, int) and not isinstance(v, bool)}


def level(state: WorldState, person: Entity, idea: str) -> int:
    """How well ``person`` holds ``idea``: 0 none, 1 aware, 3 expert."""
    node = ideas(state).get(idea)
    if node is None:
        return 0
    baseline = 1 if node.status == "common" else 0
    return max(baseline, held(person).get(idea, 0))


def missing(state: WorldState, people: list[Entity], idea: str) -> list[str]:
    """Prerequisites of ``idea`` that nobody in ``people`` holds."""
    graph = ideas(state)
    node = graph.get(idea)
    if node is None:
        return []
    return [
        need for need in node.requires
        if not any(level(state, person, need) >= 1 for person in people)
    ]


def resolve(state: WorldState, text: str | None) -> str | None:
    """An idea id for an id, a label, or a close paraphrase of one."""
    if not text or not isinstance(text, str):
        return None
    graph = ideas(state)
    if text in graph:
        return text
    wanted = slugify(text) if text.strip() else ""
    for key, idea in graph.items():
        if wanted and wanted == slugify(idea.label):
            return key
    for key, idea in graph.items():
        slug = slugify(idea.label)
        if wanted and len(wanted) >= 4 and (wanted in slug or slug in wanted):
            return key
    return None


def name_of(state: WorldState, idea: str) -> str:
    node = ideas(state).get(idea)
    return node.label if node else idea


def build(
    available: list[str],
    not_yet: list[str],
    dependencies: dict[str, list[str]] | None = None,
) -> dict[str, Idea]:
    """A graph from the technology section of a bible.

    Everything available is common. Each thing not yet invented needs the
    available things it was said to build on; with none named it needs nothing,
    and is only held back by its difficulty.
    """
    dependencies = dependencies or {}
    graph: dict[str, Idea] = {}
    for label in available:
        if label.strip():
            graph[idea_id(label)] = Idea(label=label.strip(), status="common")
    by_slug = {slugify(i.label): key for key, i in graph.items()}
    for label in not_yet:
        if not label.strip():
            continue
        key = idea_id(label)
        if key in graph:
            continue
        needs = []
        for name in dependencies.get(label, []):
            found = by_slug.get(slugify(name)) if name.strip() else None
            if found and found not in needs:
                needs.append(found)
        graph[key] = Idea(
            label=label.strip(), requires=needs, status="undiscovered",
            difficulty=min(5, 2 + len(needs)),
        )
    return graph


def pursuits(state: WorldState, person: Entity, limit: int = 4) -> list[str]:
    """Undiscovered ideas whose foundations this person already holds."""
    out = []
    for key, idea in ideas(state).items():
        if idea.status != "undiscovered":
            continue
        if missing(state, [person], key):
            continue
        out.append((idea.difficulty, key, idea))
    out.sort(key=lambda t: (t[0], t[1]))
    return [
        f"- {idea.label} [{key}], difficulty {difficulty}/5"
        for difficulty, key, idea in out[:limit]
    ]
