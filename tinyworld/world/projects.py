"""Undertakings people start for themselves, and what finishing one gives.

A project is an ordinary process with requirements. What a person proposes is
checked here against the world: items must exist, helpers must be people, an
idea to work out must be in the graph and its foundations must be held by the
people doing it. Large undertakings cannot be done alone.
"""

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.ids import slugify
from tinyworld.core.state import Entity, Fact, Process, ProcessRequirements, WorldState
from tinyworld.gm.context import name_of
from tinyworld.world import knowledge

MAX_ACTIVE = 2
MAX_DAYS = 3650
ALONE_LIMIT_DAYS = 30
WORK_DAY_MINUTES = 8 * 60
START_MINUTES = 30


def active_for(state: WorldState, person_id: str) -> list[Process]:
    return [
        p for p in state.processes.values()
        if p.status == "active" and (
            p.owner == person_id or person_id in p.requirements.participants
        )
    ]


def _new_id(state: WorldState, agent: Entity) -> str:
    base = agent.id.split(":", 1)[1]
    number = len(state.processes) + 1
    while f"process:{base}_{number}" in state.processes:
        number += 1
    return f"process:{base}_{number}"


def begin(
    state: WorldState, agent: Entity, args: dict, text: str
) -> tuple[list, str] | str:
    """Effects and narration for a new undertaking, or the reason it cannot start."""
    name = str(args.get("name") or text or "").strip()
    if not name:
        return "an undertaking needs a name"
    if len(active_for(state, agent.id)) >= MAX_ACTIVE:
        return f"{agent.name} already has {MAX_ACTIVE} undertakings going"
    days = args.get("days", 5)
    if isinstance(days, bool) or not isinstance(days, (int, float)) or days <= 0:
        return "days must be a positive number"
    days = min(float(days), MAX_DAYS)

    helpers: list[Entity] = []
    for ref in args.get("helpers") or []:
        person = state.entities.get(ref) if isinstance(ref, str) else None
        if person is None or person.kind != "person" or not person.alive:
            return f"{ref} is not someone who can help"
        if person.id != agent.id and person.id not in [h.id for h in helpers]:
            helpers.append(person)
    if days > ALONE_LIMIT_DAYS and not helpers:
        return "an undertaking this large cannot be done alone; name helpers"

    items: dict[str, int] = {}
    raw_items = args.get("items") or {}
    if not isinstance(raw_items, dict):
        return "items must map an item to a quantity"
    for ref, quantity in raw_items.items():
        item = state.entities.get(ref)
        if item is None or item.kind not in ("item", "resource"):
            return f"{ref} is not an item that exists"
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            return "item quantities must be positive whole numbers"
        items[ref] = quantity

    idea_ref = args.get("idea")
    teaches = None
    if idea_ref:
        teaches = knowledge.resolve(state, str(idea_ref))
        if teaches is None:
            return f"no idea called {idea_ref!r} is known in this world"
        graph = knowledge.ideas(state)
        if knowledge.discovered(state, teaches):
            return f"{graph[teaches].label} is already worked out"
        team = [agent] + helpers
        lacking = knowledge.missing(state, team, teaches)
        if lacking:
            names = ", ".join(knowledge.name_of(state, k) for k in lacking)
            return f"working out {graph[teaches].label} needs {names} first"
        # Harder ideas take longer, whatever was proposed.
        days = max(days, graph[teaches].difficulty * 20)
        if days > ALONE_LIMIT_DAYS and not helpers:
            return (
                f"working out {graph[teaches].label} is too large to do alone; "
                "name helpers"
            )

    place = args.get("place") or agent.location
    place_entity = state.entities.get(place) if isinstance(place, str) else None
    if place_entity is None or place_entity.kind != "place":
        return "the work needs a place"

    process = Process(
        id=_new_id(state, agent),
        name=name[:80],
        owner=agent.id,
        location=place_entity.id,
        description=text,
        requirements=ProcessRequirements(
            participants=[h.id for h in helpers], items=items,
        ),
        work_minutes=max(60, int(days * WORK_DAY_MINUTES)),
        teaches=teaches,
        builds=str(args.get('builds'))[:60] if args.get('builds') else None,
    )
    narration = f"{agent.name} sets out to {name}."
    if teaches:
        narration = (
            f"{agent.name} sets out to work out {knowledge.name_of(state, teaches)}."
        )
    return [fx.StartProcess(process=process)], narration


def skill_factor(state: WorldState, worker: Entity, process: Process) -> float:
    """0.5 to 1.5 from the worker's best aptitude. Helpers are a requirement, not a bonus."""
    persona = persona_of(worker)
    best = max(persona.aptitudes.values(), default=5) if persona else 5
    return 0.5 + max(0, min(10, best)) / 10


def completion_effects(state: WorldState, process: Process, worker: Entity) -> list:
    """Effects that follow an undertaking being completed, after EndProcess."""
    out: list = []
    if process.outcome is not None:
        out.append(fx.AssertFact(fact=process.outcome))
    if process.builds and state.grid:
        from tinyworld.genesis import layout

        owner = state.entities.get(process.owner)
        site = state.entities.get(process.location) if process.location else None
        if owner is not None:
            near = None
            if site is not None:
                from tinyworld.world import grid

                regions = grid.regions_of(state, site.id)
                if regions:
                    r = regions[0]
                    near = ((r.x0 + r.x1) // 2, (r.y0 + r.y1) // 2)
            out += layout.build_near(state, owner, process.builds, near=near or None)
    if not process.teaches:
        return out
    graph = knowledge.ideas(state)
    idea = graph.get(process.teaches)
    if idea is None:
        return out
    team = [process.owner, *process.requirements.participants, worker.id]
    for person_id in dict.fromkeys(team):
        person = state.entities.get(person_id)
        if person is None or person.kind != "person" or not person.alive:
            continue
        # A helper without the grounding sees it done but does not take it in.
        if knowledge.missing(state, [person], process.teaches):
            continue
        out.append(
            fx.LearnKnowledge(
                person=person_id, idea=process.teaches,
                level=3 if person_id == process.owner else 2, by="research",
            )
        )
    fact_id = f"fact:discovered_{slugify(idea.label)}"
    if fact_id not in state.facts:
        out.append(
            fx.AssertFact(
                fact=Fact(
                    id=fact_id,
                    text=f"{name_of(state, process.owner)} worked out {idea.label}.",
                    subject=process.owner, predicate="discovered", value=idea.label,
                )
            )
        )
    return out


def lines_for(state: WorldState, person: Entity) -> list[str]:
    """Prompt lines: this person's undertakings and ideas they could chase."""
    from tinyworld.gm import rules

    lines: list[str] = []
    for process in active_for(state, person.id):
        blockers = rules.process_blockers(state, person, process)
        status = "blocked: " + "; ".join(blockers) if blockers else "can be worked on now"
        lines.append(
            f"- {process.name} [{process.id}] {round(process.progress * 100)}% done; {status}"
        )
    chase = knowledge.pursuits(state, person)
    out: list[str] = []
    if lines:
        out += ["", "Your undertakings:"] + lines
    if chase and len(active_for(state, person.id)) < MAX_ACTIVE:
        out += ["", "Ideas you have the grounding to work out (use verb start):"] + chase
    return out
