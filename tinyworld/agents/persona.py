"""Who an agent is, and the limits of what they can know."""

from pydantic import Field

from tinyworld.core.state import Entity, Model


# Below this age a person is part of the background, not a deciding agent.
AGENT_AGE = 14


class KnowledgeBoundary(Model):
    """What a person of this time, place, class and schooling could know."""

    era: str = ""
    education: str = ""
    knows: list[str] = Field(default_factory=list)
    does_not_know: list[str] = Field(default_factory=list)


class Persona(Model):
    summary: str = Field(min_length=1)
    traits: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    aptitudes: dict[str, int] = Field(default_factory=dict)
    speech_style: str = ""
    knowledge: KnowledgeBoundary = Field(default_factory=KnowledgeBoundary)


def persona_of(entity: Entity) -> Persona | None:
    raw = entity.attrs.get("persona")
    if not isinstance(raw, dict):
        return None
    try:
        return Persona.model_validate(raw)
    except ValueError:
        return None


def _line(label: str, items: list[str]) -> str | None:
    return f"{label}: {'; '.join(items)}" if items else None


def render(entity: Entity, persona: Persona) -> str:
    """The persona as prompt text. Stable across ticks unless the persona changes."""
    knowledge = persona.knowledge
    lines = [
        f"You are {entity.name} [{entity.id}]. {persona.summary}",
        _line("Traits", persona.traits),
        _line("You value", persona.values),
        _line("You want", persona.goals),
        _line("You fear", persona.fears),
        _line("Secrets you keep", persona.secrets),
        _line(
            "Natural aptitudes",
            [f"{name} {level}/10" for name, level in sorted(persona.aptitudes.items())],
        ),
        f"How you speak: {persona.speech_style}" if persona.speech_style else None,
        "",
        "What you can know:",
        f"- You live in: {knowledge.era}" if knowledge.era else None,
        f"- Schooling: {knowledge.education}" if knowledge.education else None,
        _line("- You know about", knowledge.knows),
        _line("- You know nothing of", knowledge.does_not_know),
        "- Anything not learned from your own life, or seen or heard in this world, "
        "is unknown to you. Never draw on knowledge from outside it.",
    ]
    return "\n".join(line for line in lines if line is not None)
