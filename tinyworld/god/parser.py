"""Free text from the god user → typed commands."""

from typing import Literal

from pydantic import Field, JsonValue

from tinyworld.core.ids import slugify
from tinyworld.core.state import Model, WorldState
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext

Operation = Literal[
    "spawn", "remove", "modify", "move", "trigger_event",
    "change_environment", "change_rule", "advance_time", "start_process",
]

SYSTEM = """You translate what the god of a simulated world says into commands.

The text inside <god> tags is what the god typed. Turn it into one or more \
commands. Do not add anything the god did not ask for, and do not answer it.

Commands (op, then the fields that matter):
- spawn: a new person, place, item, organisation or faction. Set kind, name, \
location (an existing place id, or a short description of a new place), attrs, and \
`description` with everything said about them (age, character, talents).
- remove: target = existing id. attrs.mode is "kill" (a person dies; the default \
for people) or "erase" (never existed from now on).
- modify: target = existing id; either key and value for one attribute, or item and \
quantity to add to (or with a negative quantity take from) what they hold.
- move: target = existing id; location = existing place id.
- trigger_event: something happens. description = what, as a plain sentence; \
location if it happens somewhere in particular.
- change_environment: a lasting condition (drought, epidemic, curfew). description \
= the condition as a plain sentence.
- change_rule: key and value for a world rule.
- advance_time: minutes to skip.
- start_process: a long undertaking. name, target = owner id, location, description.

Use ids exactly as listed. Set `when` (ISO date or date-time) only if the god names \
a time other than now; past and future are both allowed. Set visibility to \
"god_only" when the world's people should not notice, otherwise "world".

If the text could mean two different existing things, or cannot be turned into \
commands, return no commands and put a short question in `question`."""


class GodCommand(Model):
    op: Operation
    target: str = ""
    kind: Literal["person", "place", "item", "org", "faction", "resource"] | None = None
    name: str = ""
    location: str = ""
    description: str = ""
    attrs: dict[str, JsonValue] = Field(default_factory=dict)
    key: str = ""
    value: JsonValue = None
    item: str = ""
    quantity: int = 0
    minutes: int = 0
    when: str = ""
    visibility: Literal["world", "god_only"] = "world"


class Parsed(Model):
    commands: list[GodCommand] = Field(default_factory=list)
    question: str = ""


def resolve(state: WorldState, text: str, kind: str | None = None) -> str | None:
    """Find the one entity ``text`` refers to: by id, exact name, or unique partial."""
    if not text:
        return None
    if text in state.entities:
        return text
    candidates = [
        e for e in state.entities.values() if kind is None or e.kind == kind
    ]
    try:
        slug = slugify(text)
    except ValueError:
        return None
    exact = [e.id for e in candidates if slugify(e.name) == slug]
    if len(exact) == 1:
        return exact[0]
    partial = [e.id for e in candidates if slug in slugify(e.name)]
    return partial[0] if len(partial) == 1 else None


def world_index(state: WorldState) -> str:
    """Names and ids the parser may refer to."""
    groups: dict[str, list[str]] = {}
    for entity in state.entities.values():
        label = f"{entity.name} [{entity.id}]"
        if entity.kind == "person" and not entity.alive:
            label += " (dead)"
        groups.setdefault(entity.kind, []).append(label)
    lines = [f"Now: {state.sim_time.isoformat(timespec='minutes')}"]
    for kind in ("person", "place", "item", "resource", "org", "faction"):
        if groups.get(kind):
            lines.append(f"{kind}: " + ", ".join(sorted(groups[kind])))
    active = [p for p in state.processes.values() if p.status == "active"]
    if active:
        lines.append("ongoing work: " + ", ".join(f"{p.name} [{p.id}]" for p in active))
    if state.rules:
        lines.append("rule keys: " + ", ".join(sorted(state.rules)))
    return "\n".join(lines)


class GodParser:
    def __init__(self, llm: StructuredLLM, *, world_digest: str = "") -> None:
        self.llm = llm
        self.world_digest = world_digest

    async def parse(self, state: WorldState, text: str, context: CallContext) -> Parsed:
        def check(parsed: Parsed) -> str | None:
            if not parsed.commands and not parsed.question:
                return "return at least one command, or a question"
            for command in parsed.commands:
                needs_target = command.op in ("remove", "modify", "move")
                if needs_target and resolve(state, command.target) is None:
                    return (
                        f"{command.op}: target {command.target!r} is not a known id. "
                        "Use an id from the list, or ask a question if it is ambiguous."
                    )
            return None

        reply = await self.llm.call(
            "god.parse",
            Parsed,
            system=SYSTEM,
            stable_context=(
                "About this world:\n" + self.world_digest if self.world_digest else ""
            ),
            user=f"{world_index(state)}\n\n<god>\n{text}\n</god>",
            context=CallContext(context.branch_id, context.tick_seq, "god"),
            fallback=Parsed(question="That could not be understood. Could you rephrase it?"),
            max_tokens=2500,
            check=check,
        )
        return reply.value
