"""Who perceives an event, how, and how reliably.

Ported from v1's ObservationSystem. Reach comes from the place graph: a
neighbouring place sees an event only across a visible edge and hears it only
across an audible one, and only when the event is loud.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from tinyworld.core import effects as fx
from tinyworld.core.effects import Claim
from tinyworld.core.events import Event
from tinyworld.core.state import Model, WorldState
from tinyworld.gm.context import name_of

Mode = Literal["self", "visual", "auditory", "public"]

CONFIDENCE = {
    "self": 1.0,
    "present": 1.0,
    "overheard": 0.7,
    "seen_from_afar": 0.6,
    "heard_from_afar": 0.5,
    "public": 0.9,
}
_PRIORITY = {"self": 0, "visual": 1, "auditory": 2, "public": 3}


class Observation(Model):
    observer: str
    event_seq: int
    sim_time: datetime
    mode: Mode
    confidence: float = Field(ge=0.0, le=1.0)
    text: str
    location: str | None = None
    actor: str = ""
    participants: list[str] = Field(default_factory=list)
    # What was said. Claims may be false; the observer only knows they were made.
    claims: list[Claim] = Field(default_factory=list)
    # What was plainly witnessed to happen.
    facts: list[Claim] = Field(default_factory=list)
    speaker: str | None = None
    addressed: bool = False


def _utterances(event: Event) -> list[fx.Utter]:
    return [effect for effect in event.effects if isinstance(effect, fx.Utter)]


def _participants(event: Event) -> list[str]:
    found: list[str] = []
    if event.actor.startswith("person:"):
        found.append(event.actor)
    for effect in event.effects:
        for field in ("entity", "source", "dest", "speaker", "holder"):
            value = getattr(effect, field, None)
            if isinstance(value, str) and value.startswith("person:"):
                found.append(value)
        found.extend(getattr(effect, "addressees", []))
    return list(dict.fromkeys(found))


def _witnessed_facts(event: Event) -> list[Claim]:
    """Facts anyone watching the event closely would come away knowing."""
    facts: list[Claim] = []
    for effect in event.effects:
        if isinstance(effect, fx.MoveEntity):
            facts.append(Claim(subject=effect.entity, predicate="location", value=effect.to))
        elif isinstance(effect, fx.Kill):
            facts.append(Claim(subject=effect.entity, predicate="alive", value=False))
    return facts


def _is_loud(event: Event) -> bool:
    if event.loud:
        return True
    if any(isinstance(effect, fx.Kill) for effect in event.effects):
        return True
    return any(u.channel in ("audible", "public") for u in _utterances(event))


def perceive(event: Event, state: WorldState) -> list[Observation]:
    """Observations produced by ``event``, given the state right after it."""
    if event.visibility == "god_only":
        return []

    utterances = _utterances(event)
    participants = _participants(event)
    speech_claims = [claim for u in utterances for claim in u.claims]
    witnessed = _witnessed_facts(event)
    addressees = {a for u in utterances for a in u.addressees}
    speaker = utterances[0].speaker if utterances else None
    text = event.narration or f"Something happened involving {name_of(state, event.actor)}."

    def observation(observer: str, mode: Mode, confidence: float, **changes) -> Observation:
        fields = dict(
            observer=observer,
            event_seq=event.seq,
            sim_time=event.sim_time,
            mode=mode,
            confidence=confidence,
            text=text,
            location=event.location,
            actor=event.actor,
            participants=participants,
            claims=speech_claims,
            speaker=speaker,
            addressed=observer in addressees,
        )
        fields.update(changes)
        # Facts are only certain to someone who saw the event itself.
        clear_view = fields["mode"] in ("self", "public") or (
            fields["mode"] == "visual" and fields["text"] == text
        )
        fields.setdefault("facts", witnessed if clear_view else [])
        return Observation(**fields)

    found: dict[str, Observation] = {}

    def add(candidate: Observation) -> None:
        current = found.get(candidate.observer)
        if current is None or candidate.confidence > current.confidence:
            found[candidate.observer] = candidate

    actor = state.entities.get(event.actor)
    if actor is not None and actor.kind == "person" and actor.alive:
        add(observation(actor.id, "self", CONFIDENCE["self"]))

    living = [p for p in state.people() if p.location is not None]

    if event.visibility == "public":
        for person in living:
            add(observation(person.id, "public", CONFIDENCE["public"]))
        return list(found.values())

    if event.visibility == "secret":
        involved = set(participants)
        for person in living:
            if person.id in involved and person.location == event.location:
                add(observation(person.id, "visual", CONFIDENCE["present"]))
        return list(found.values())

    # "witnessed": perceived by whoever is in a position to perceive it.
    scenes = [event.location] if event.location else []
    for effect in event.effects:
        if isinstance(effect, fx.MoveEntity) and effect.to not in scenes:
            scenes.append(effect.to)  # an arrival is seen where it ends
    if not scenes:
        return list(found.values())

    private_speech = bool(utterances) and all(u.channel == "direct" for u in utterances)
    loud = _is_loud(event)
    place_name = name_of(state, scenes[0])

    for person in living:
        if person.location in scenes:
            if private_speech and addressees and person.id not in addressees:
                add(observation(person.id, "auditory", CONFIDENCE["overheard"]))
            else:
                add(observation(person.id, "visual", CONFIDENCE["present"]))
            continue
        for scene in scenes:
            edge = state.edge(person.location, scene)
            if edge is None:
                continue
            sees = edge.visible
            hears = edge.audible and loud
            if utterances:
                if hears:
                    # The words carry; seeing the speaker makes them surer.
                    add(
                        observation(
                            person.id, "auditory",
                            CONFIDENCE["seen_from_afar" if sees else "heard_from_afar"],
                        )
                    )
                elif sees:
                    add(
                        observation(
                            person.id, "visual", CONFIDENCE["seen_from_afar"],
                            text=f"{name_of(state, event.actor)} is talking at {place_name}.",
                            claims=[],
                        )
                    )
            elif sees:
                add(observation(person.id, "visual", CONFIDENCE["seen_from_afar"]))
            elif hears:
                add(
                    observation(
                        person.id, "auditory", CONFIDENCE["heard_from_afar"],
                        text=f"A commotion is heard from {place_name}.",
                        participants=[],
                    )
                )
    return list(found.values())


def limit_attention(observations: list[Observation], limit: int) -> list[Observation]:
    """Keep the ``limit`` most salient observations, in time order."""
    if limit <= 0:
        return []
    ranked = sorted(
        observations,
        key=lambda o: (not o.addressed, _PRIORITY[o.mode], -o.confidence, -o.event_seq),
    )[:limit]
    return sorted(ranked, key=lambda o: o.event_seq)
