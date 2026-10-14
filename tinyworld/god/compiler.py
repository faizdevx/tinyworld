"""God commands → events. The only way a god action reaches the world."""

from datetime import timedelta

from pydantic import Field

from tinyworld.agents.persona import KnowledgeBoundary, Persona
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.ids import make_id, slugify
from tinyworld.core.state import Entity, Fact, Model, PlaceEdge, Process, WorldState
from tinyworld.god.feasibility import Judgement, hub_place
from tinyworld.god.parser import GodCommand
from tinyworld.llm.structured import StructuredLLM
from tinyworld.llm.types import CallContext

# Below this age a person is part of the background, not a deciding agent.
AGENT_AGE = 14

PERSONA_SYSTEM = """You write the character sheet for a person who is being added to a \
simulated world.

- They belong to this world and this moment. Their knowledge is what someone of their \
age, place, class and schooling here could have. A newborn or small child knows \
nothing yet: leave `knows` empty and give no goals beyond a child's.
- Aptitudes are inborn leanings (1 to 10) and may be set at any age.
- If the request names a real historical person, this is a new person who shares \
that name and those gifts, born into this world. They have none of the historical \
person's life, discoveries or knowledge. Say so in `explanation`.
- Give adults conflicting wants, a fear and, where it fits, a secret.
- `explanation` is one or two sentences telling the god what was created."""


class SpawnProfile(Model):
    age: int = Field(ge=0, le=120)
    occupation: str = ""
    persona: Persona
    explanation: str = ""


def _era(state: WorldState) -> str:
    era = state.rules.get("era")
    return era if isinstance(era, str) else ""


def default_profile(state: WorldState, command: GodCommand) -> SpawnProfile:
    age = command.attrs.get("age")
    age = age if isinstance(age, int) and not isinstance(age, bool) else 30
    child = age < AGENT_AGE
    return SpawnProfile(
        age=age,
        occupation=str(command.attrs.get("occupation", "")),
        persona=Persona(
            summary=command.description or f"{command.name}, newly arrived.",
            knowledge=KnowledgeBoundary(
                era=_era(state),
                does_not_know=["almost everything; still a child"] if child else [],
            ),
        ),
        explanation=f"{command.name} was created.",
    )


async def build_profile(
    llm: StructuredLLM | None,
    state: WorldState,
    command: GodCommand,
    context: CallContext,
    world_digest: str = "",
) -> SpawnProfile:
    fallback = default_profile(state, command)
    if llm is None:
        return fallback
    reply = await llm.call(
        "agent.persona",
        SpawnProfile,
        system=PERSONA_SYSTEM,
        stable_context="About this world:\n" + world_digest if world_digest else "",
        user=(
            f"Now: {state.sim_time:%d %B %Y}. Era: {_era(state) or 'see above'}.\n"
            f"Name: {command.name}\n"
            f"What the god said about them: {command.description or '(nothing more)'}\n"
            f"Given attributes: {command.attrs or '(none)'}"
        ),
        context=CallContext(context.branch_id, context.tick_seq, "god:persona"),
        fallback=fallback,
        max_tokens=2000,
    )
    profile = reply.value
    if not profile.persona.knowledge.era:
        profile.persona.knowledge.era = _era(state)
    return profile


def _visibility(command: GodCommand, located: bool) -> str:
    if command.visibility == "god_only":
        return "god_only"
    return "witnessed" if located else "public"


def compile_command(
    state: WorldState,
    judgement: Judgement,
    profile: SpawnProfile | None = None,
) -> list[EventDraft]:
    """Events for one judged command. Raises ValueError for a rejected one."""
    if judgement.verdict == "reject":
        raise ValueError("a rejected command cannot be compiled")
    command = judgement.command
    op = command.op

    def draft(effects, narration, *, location=None, visibility=None, loud=False):
        return EventDraft(
            kind="god",
            actor="god",
            location=location,
            effects=effects,
            narration=narration,
            visibility=visibility or _visibility(command, location is not None),
            loud=loud,
        )

    if op == "spawn":
        new_id = make_id(command.kind, command.name)
        effects: list = []
        location = command.location or None

        if location and location.startswith("new:"):
            house_name = location[4:]
            location = make_id("place", house_name)
            effects.append(
                fx.CreateEntity(
                    entity=Entity(
                        id=location, kind="place", name=house_name,
                        attrs={"place_type": "house", "description": f"The home of {command.name}."},
                    )
                )
            )
            hub = hub_place(state)
            if hub is not None:
                effects.append(
                    fx.SetEdge(a=location, b=hub, edge=PlaceEdge(travel_minutes=10))
                )

        attrs = dict(command.attrs)
        if command.kind == "person":
            profile = profile or default_profile(state, command)
            born = state.sim_time - timedelta(days=round(profile.age * 365.25))
            attrs.update(
                age=profile.age,
                birth_date=born.date().isoformat(),
                home=location,
                tier=0 if profile.age >= AGENT_AGE else 2,
                persona=profile.persona.model_dump(),
            )
            if profile.occupation:
                attrs["occupation"] = profile.occupation
            narration = (
                f"A child, {command.name}, is born."
                if profile.age == 0
                else f"{command.name} arrives."
            )
        else:
            if command.description and "description" not in attrs:
                attrs["description"] = command.description
            narration = f"{command.name} appears."

        effects.append(
            fx.CreateEntity(
                entity=Entity(
                    id=new_id, kind=command.kind, name=command.name,
                    location=location if command.kind in ("person", "item") else None,
                    attrs=attrs,
                )
            )
        )
        if command.kind == "place" and location:
            effects.append(fx.SetEdge(a=new_id, b=location, edge=PlaceEdge(travel_minutes=10)))
        where = location if command.kind in ("person", "item") else None
        return [draft(effects, narration, location=where)]

    if op == "remove":
        entity = state.entities[command.target]
        if command.attrs["mode"] == "kill":
            cause = command.description or "an act of god"
            return [
                draft(
                    [fx.Kill(entity=entity.id, cause=cause)],
                    f"{entity.name} dies.",
                    location=entity.location,
                    loud=True,
                )
            ]
        return [
            draft(
                [fx.RemoveEntity(entity=entity.id)],
                f"{entity.name} is gone.",
                visibility="god_only",
            )
        ]

    if op == "modify":
        entity = state.entities[command.target]
        if command.item:
            effect = fx.ChangeQuantity(
                holder=entity.id, item=command.item, delta=command.quantity
            )
        else:
            effect = fx.SetAttr(entity=entity.id, key=command.key, value=command.value)
        # A silent edit of the world: nobody sees it happen.
        return [draft([effect], f"{entity.name} is changed.", visibility="god_only")]

    if op == "move":
        entity = state.entities[command.target]
        destination = state.entities[command.location]
        return [
            draft(
                [fx.MoveEntity(entity=entity.id, to=destination.id)],
                f"{entity.name} is suddenly at {destination.name}.",
                location=entity.location,
            )
        ]

    if op == "trigger_event":
        return [
            draft([], command.description, location=command.location or None, loud=True)
        ]

    if op == "change_environment":
        fact_id = "fact:" + slugify(command.description)[:48].rstrip("_")
        suffix = 2
        base = fact_id
        while fact_id in state.facts and state.fact_holds(fact_id):
            fact_id = f"{base}_{suffix}"
            suffix += 1
        return [
            draft(
                [fx.AssertFact(fact=Fact(id=fact_id, text=command.description))],
                command.description,
                location=command.location or None,
            )
        ]

    if op == "change_rule":
        return [
            draft(
                [fx.SetRule(key=command.key, value=command.value)],
                f"The rule {command.key} is now {command.value}.",
                visibility="god_only",
            )
        ]

    if op == "advance_time":
        return [
            draft(
                [fx.AdvanceTime(minutes=command.minutes)],
                "Time passes.",
                visibility="god_only",
            )
        ]

    if op == "start_process":
        work_minutes = command.attrs.get("work_minutes")
        process = Process(
            id="process:" + slugify(command.name),
            name=command.name,
            owner=command.target,
            location=command.location or None,
            description=command.description,
            work_minutes=work_minutes
            if isinstance(work_minutes, int) and work_minutes > 0
            else 600,
        )
        owner = state.entities[command.target]
        return [
            draft(
                [fx.StartProcess(process=process)],
                f"{owner.name} begins: {command.name}.",
                location=command.location or owner.location,
            )
        ]

    raise ValueError(f"unsupported god operation: {op}")
