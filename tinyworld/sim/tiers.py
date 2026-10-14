"""Tiers decide who thinks, how often and how expensively.

Tier 0 decides every tick on the standard model. Tier 1 decides every few
ticks on the cheap model with a shorter context. Tier 2 has no individual
cognition: factions and districts drift by simple rules.
"""

import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import Event, EventDraft
from tinyworld.core.rng import seeded
from tinyworld.core.state import Entity, WorldState
from tinyworld.core.store import Store
from tinyworld.god.compiler import AGENT_AGE

EPOCH = datetime(1, 1, 1)


def tier_of(entity: Entity) -> int:
    tier = entity.attrs.get("tier", 0)
    return tier if isinstance(tier, int) and not isinstance(tier, bool) else 0


def age_of(entity: Entity, now: datetime) -> int | None:
    born = entity.attrs.get("birth_date")
    if isinstance(born, str):
        try:
            birth = datetime.fromisoformat(born)
        except ValueError:
            birth = None
        if birth is not None:
            years = now.year - birth.year
            if (now.month, now.day) < (birth.month, birth.day):
                years -= 1
            return max(0, years)
    age = entity.attrs.get("age")
    return age if isinstance(age, int) and not isinstance(age, bool) else None


def old_enough(entity: Entity, now: datetime) -> bool:
    age = age_of(entity, now)
    return age is None or age >= AGENT_AGE


@dataclass
class TierPolicy:
    tier1_every: int = 4
    idle_events: int = 24
    tier2_every_minutes: int = 24 * 60
    promote_involved: bool = True

    def tier1_turn(self, agent_id: str, now: datetime, step_minutes: int) -> bool:
        """Whether a tier-1 agent acts this tick. Staggered so they do not all act at once."""
        tick_index = int((now - EPOCH).total_seconds() // 60) // max(step_minutes, 1)
        offset = zlib.crc32(agent_id.encode()) % self.tier1_every
        return tick_index % self.tier1_every == offset

    def demotions(self, store: Store, branch_id: str, state: WorldState) -> list[str]:
        """Tier-0 agents whose recent actions have all come to nothing."""
        idle = []
        for person in state.people():
            if tier_of(person) != 0 or persona_of(person) is None:
                continue
            recent = store.events(
                branch_id, actor=person.id, limit=self.idle_events, newest_first=True
            )
            if len(recent) >= self.idle_events and not any(e.effects for e in recent):
                idle.append(person.id)
        return idle

    def involved(self, state: WorldState, events: list[Event]) -> list[str]:
        """Lower-tier people drawn into events that a tier-0 agent caused."""
        from tinyworld.gm.perception import _participants

        found: list[str] = []
        if not self.promote_involved:
            return found
        for event in events:
            actor = state.entities.get(event.actor)
            if actor is None or actor.kind != "person" or tier_of(actor) != 0:
                continue
            for participant in _participants(event):
                other = state.entities.get(participant)
                if (
                    other is not None
                    and other.id != actor.id
                    and other.alive
                    and tier_of(other) != 0
                    and old_enough(other, state.sim_time)
                    and other.id not in found
                ):
                    found.append(other.id)
        return found


def tier_draft(changes: dict[str, int], reason: str) -> EventDraft:
    return EventDraft(
        kind="system",
        actor="system",
        visibility="god_only",
        effects=[
            fx.SetAttr(entity=entity, key="tier", value=tier)
            for entity, tier in sorted(changes.items())
        ],
        narration=reason,
    )


def background_drift(state: WorldState, seed: str, periods: int = 1) -> EventDraft | None:
    """Statistical update of factions and organisations between LLM summaries.

    Morale sags under each standing hardship and otherwise wanders; influence
    follows morale slowly. Deliberately crude: the point is that the
    background is not frozen while nobody is looking at it.
    """
    hardships = sum(
        1
        for fact in state.active_facts()
        if any(word in fact.text.lower() for word in ("drought", "famine", "shortage", "epidemic", "cut"))
    )
    effects = []
    for entity in sorted(state.entities.values(), key=lambda e: e.id):
        if entity.kind not in ("faction", "org"):
            continue
        rng = seeded(seed, "drift", state.seq, entity.id)
        morale = entity.attrs.get("morale")
        morale = morale if isinstance(morale, int) else 50
        change = sum(rng.randint(-3, 3) - hardships for _ in range(periods))
        new_morale = min(100, max(0, morale + change))
        if new_morale != morale:
            effects.append(fx.SetAttr(entity=entity.id, key="morale", value=new_morale))
        if entity.kind == "faction":
            influence = entity.attrs.get("influence")
            if isinstance(influence, int):
                pull = (new_morale - 50) // 25
                new_influence = min(100, max(0, influence + pull * periods))
                if new_influence != influence:
                    effects.append(
                        fx.SetAttr(entity=entity.id, key="influence", value=new_influence)
                    )
    if not effects:
        return None
    return EventDraft(
        kind="system", actor="system", visibility="god_only",
        effects=effects, narration="Background drift.",
    )


def birth_date_for(now: datetime, age: int) -> str:
    return (now - timedelta(days=round(age * 365.25))).date().isoformat()


def birth_dates_draft(state: WorldState) -> EventDraft | None:
    """Give a birth date to anyone who only has an age, so that they can age."""
    effects = [
        fx.SetAttr(
            entity=person.id, key="birth_date",
            value=birth_date_for(state.sim_time, person.attrs["age"]),
        )
        for person in sorted(state.people(), key=lambda p: p.id)
        if "birth_date" not in person.attrs
        and isinstance(person.attrs.get("age"), int)
        and not isinstance(person.attrs.get("age"), bool)
    ]
    if not effects:
        return None
    return EventDraft(
        kind="system", actor="system", visibility="god_only",
        effects=effects, narration="Birth dates recorded.",
    )


def aging_draft(state: WorldState) -> EventDraft | None:
    """Bring stored ages up to date with the calendar."""
    effects = [
        fx.SetAttr(entity=person.id, key="age", value=age)
        for person in sorted(state.people(), key=lambda p: p.id)
        if (age := age_of(person, state.sim_time)) is not None
        and person.attrs.get("age") != age
    ]
    if not effects:
        return None
    return EventDraft(
        kind="system", actor="system", visibility="god_only",
        effects=effects, narration="Ages updated.",
    )
