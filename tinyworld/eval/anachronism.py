"""Finding things said or created that this world does not have yet."""

import re
from dataclasses import dataclass

from tinyworld.core import effects as fx
from tinyworld.core.state import WorldState
from tinyworld.core.store import Store


@dataclass(frozen=True)
class Anachronism:
    seq: int
    term: str
    where: str
    text: str
    by_god: bool


def not_yet_terms(state: WorldState) -> list[str]:
    terms = state.rules.get("tech.not_yet") or []
    return [t for t in terms if isinstance(t, str) and t.strip()]


def _pattern(terms: list[str]) -> re.Pattern | None:
    if not terms:
        return None
    # Match on the distinctive head of each entry: "television in homes" is
    # found by "television", "radar known to the public" by "radar".
    heads = sorted(
        {re.escape(term.lower().split(" in ")[0].split(" known ")[0].strip()) for term in terms},
        key=len,
        reverse=True,
    )
    return re.compile(r"(?<![a-z])(" + "|".join(heads) + r")(?![a-z])", re.IGNORECASE)


def scan(store: Store, branch_id: str, state: WorldState | None = None) -> list[Anachronism]:
    """Utterances and created things that mention technology marked as not yet existing.

    Mentions the god introduced are reported but flagged: those are the user's
    own choice, not a leak from the model.
    """
    state = state or store.state_at(branch_id)
    pattern = _pattern(not_yet_terms(state))
    if pattern is None:
        return []
    found: list[Anachronism] = []
    for event in store.events(branch_id):
        by_god = event.actor == "god"
        for effect in event.effects:
            if isinstance(effect, fx.Utter):
                candidates = [("said", effect.text)]
            elif isinstance(effect, fx.CreateEntity):
                description = effect.entity.attrs.get("description")
                candidates = [("created", effect.entity.name)]
                if isinstance(description, str):
                    candidates.append(("created", description))
            elif isinstance(effect, fx.StartProcess):
                candidates = [("begun", f"{effect.process.name} {effect.process.description}")]
            elif isinstance(effect, fx.AssertFact):
                candidates = [("asserted", effect.fact.text)]
            else:
                continue
            for where, text in candidates:
                match = pattern.search(text)
                if match:
                    found.append(
                        Anachronism(event.seq, match.group(1).lower(), where, text, by_god)
                    )
    return found


def leaks(found: list[Anachronism]) -> list[Anachronism]:
    """Anachronisms the model produced, as opposed to ones the god asked for."""
    return [item for item in found if not item.by_god]
