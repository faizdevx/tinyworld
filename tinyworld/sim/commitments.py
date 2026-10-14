"""Promises falling due: kept or broken, and what that does to trust."""

from datetime import timedelta

from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.state import Commitment, WorldState
from tinyworld.core.store import Store
from tinyworld.gm.context import name_of

KEPT_TRUST = 6
BROKEN_TRUST = -15


def _given(store: Store, branch_id: str, commitment: Commitment) -> int:
    """How much of the promised item has gone from the promiser to the other."""
    after = commitment.made_seq or store.seq_at_time(branch_id, commitment.made_at)
    total = 0
    for event in store.events(branch_id, after=after):
        for effect in event.effects:
            if (
                isinstance(effect, fx.TransferItem)
                and effect.item == commitment.item
                and effect.source == commitment.by
                and effect.dest == commitment.to
            ):
                total += effect.quantity
    return total


def outcome(
    state: WorldState, store: Store, branch_id: str, commitment: Commitment
) -> str:
    """kept, broken or released, for a commitment that is due."""
    debtor = state.entities.get(commitment.by)
    creditor = state.entities.get(commitment.to)
    if debtor is None or not debtor.alive or creditor is None or not creditor.alive:
        return "released"
    if commitment.kind == "meet":
        return "kept" if debtor.location == commitment.place else "broken"
    return "kept" if _given(store, branch_id, commitment) >= commitment.quantity else "broken"


def due(state: WorldState, within: timedelta = timedelta(0)) -> list[Commitment]:
    horizon = state.sim_time + within
    return [c for c in state.open_commitments() if c.due <= horizon]


def due_soon_for(state: WorldState, person: str, within: timedelta) -> list[Commitment]:
    return [c for c in due(state, within) if c.by == person]


def settle(
    state: WorldState, store: Store, branch_id: str
) -> list[tuple[EventDraft, list[tuple[str, str]]]]:
    """Resolution drafts for every commitment now due, with a note per person."""
    results = []
    for commitment in due(state):
        status = outcome(state, store, branch_id, commitment)
        by, to = name_of(state, commitment.by), name_of(state, commitment.to)
        effects: list = [
            fx.ResolveCommitment(commitment_id=commitment.id, status=status)
        ]
        notes: list[tuple[str, str]] = []
        if status == "kept":
            narration = f"{by} kept a promise to {to}: {commitment.text}"
            notes = [
                (commitment.by, f"I kept my promise to {to}: {commitment.text}"),
                (commitment.to, f"{by} kept their promise: {commitment.text}"),
            ]
            delta = KEPT_TRUST
        elif status == "broken":
            narration = f"{by} broke a promise to {to}: {commitment.text}"
            notes = [
                (commitment.by, f"I did not keep my promise to {to}: {commitment.text}"),
                (commitment.to, f"{by} broke their promise to me: {commitment.text}"),
            ]
            delta = BROKEN_TRUST
        else:
            narration = f"A promise from {by} to {to} lapsed: {commitment.text}"
            delta = 0
        if delta and commitment.to in state.entities and commitment.by in state.entities:
            current = state.relation(commitment.to, commitment.by)
            value = max(-100, min(100, (current.value if current else 0) + delta))
            effects.append(
                fx.SetRelation(
                    source=commitment.to, dest=commitment.by,
                    kind=current.kind if current else "acquaintance",
                    value=value, note=current.note if current else "",
                )
            )
        results.append(
            (
                EventDraft(
                    kind="system", actor="system", visibility="god_only",
                    effects=effects, narration=narration,
                ),
                notes,
            )
        )
    return results


def lines_for(state: WorldState, person: str) -> list[str]:
    """Prompt lines for a person's open promises, in either direction."""
    lines = []
    for c in state.open_commitments(person):
        by, to = name_of(state, c.by), name_of(state, c.to)
        if c.by == person:
            lines.append(f"- You promised {to}: {c.text} (by {c.due:%a %d %b %H:%M})")
        else:
            lines.append(f"- {by} promised you: {c.text} (by {c.due:%a %d %b %H:%M})")
    return lines
