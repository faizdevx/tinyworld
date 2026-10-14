"""Grouping of same-tick intents that interfere with each other."""

from tinyworld.core.events import Intent
from tinyworld.core.state import WorldState
from tinyworld.gm.verbs import CONTESTED


def _keys(state: WorldState, intent: Intent) -> set[str]:
    """Things this intent touches. Two intents sharing a key interfere."""
    keys = {f"person#{intent.agent}"}
    target = intent.target
    item = intent.args.get("item")
    if intent.verb in CONTESTED:
        holder = target or state.entities[intent.agent].location
        # Two people taking different goods from one shelf do not collide.
        keys.add(f"{holder}#{item}" if isinstance(item, str) else f"{holder}#")
    # Acting on a person collides with whatever that person is doing.
    if target and target in state.entities and state.entities[target].kind == "person":
        keys.add(f"person#{target}")
    return keys


def group(state: WorldState, intents: list[Intent]) -> list[list[Intent]]:
    """Partition intents into independent groups, preserving input order.

    Intents in different groups cannot affect each other and may be resolved
    concurrently. A group of one needs no joint decision.
    """
    parent = list(range(len(intents)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    owners: dict[str, int] = {}
    for index, intent in enumerate(intents):
        for key in _keys(state, intent):
            if key in owners:
                parent[find(index)] = find(owners[key])
            else:
                owners[key] = index

    groups: dict[int, list[Intent]] = {}
    for index, intent in enumerate(intents):
        groups.setdefault(find(index), []).append(intent)
    return list(groups.values())
