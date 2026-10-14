"""The single write path for a branch."""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tinyworld.core.events import Event, EventDraft
from tinyworld.core.registry import REGISTRY, AttrRegistry
from tinyworld.core.reducers import EffectError, apply_event_in_place, end_time
from tinyworld.core.state import WorldState
from tinyworld.core.store import Store


class CommitError(RuntimeError):
    pass


class InvariantError(RuntimeError):
    """A committed event broke an invariant. Raised only in debug mode."""


@dataclass
class CommitResult:
    events: list[Event] = field(default_factory=list)
    observed: list[Any] = field(default_factory=list)
    rejected: list[tuple[EventDraft, str]] = field(default_factory=list)


class WorldSession:
    """Holds the current state of one branch and commits events to it.

    There must be one session writing to a branch at a time. Nothing else may
    change state: every change is an event that passes through ``commit``.
    """

    def __init__(
        self,
        store: Store,
        branch_id: str,
        *,
        registry: AttrRegistry = REGISTRY,
        snapshot_every: int = 200,
        debug: bool | None = None,
    ) -> None:
        self.store = store
        self.branch_id = branch_id
        self.registry = registry
        self.snapshot_every = snapshot_every
        # In debug mode every committed event is checked against the
        # invariants in tinyworld.eval.invariants, and a violation aborts.
        self.debug = (
            bool(os.environ.get("TINYWORLD_DEBUG")) if debug is None else debug
        )
        self.state: WorldState = store.state_at(branch_id, registry=registry)

    @property
    def world_id(self) -> str:
        return self.store.branch(self.branch_id)["world_id"]

    def commit(
        self,
        drafts: list[EventDraft],
        *,
        atomic: bool = True,
        observe: Callable[[Event, WorldState], Any] | None = None,
    ) -> CommitResult:
        """Apply drafts in order and store the resulting events.

        With ``atomic`` a failing draft aborts the whole batch and nothing is
        stored. Without it, failing drafts are skipped and reported.

        ``observe`` is called after each applied event with the state at that
        moment. It must not have side effects, because an aborted batch
        discards what it returned.
        """
        working = self.state.model_copy(deep=True)
        result = CommitResult()
        for draft in drafts:
            event = Event(
                **draft.model_dump(),
                branch_id=self.branch_id,
                seq=working.seq + 1,
                sim_time=end_time(working, draft.effects),
            )
            backup = None if atomic else working.model_copy(deep=True)
            try:
                if any(not 0 < cause < event.seq for cause in event.causes):
                    raise EffectError("an event can only be caused by earlier events")
                before = working.model_copy(deep=True) if self.debug else None
                apply_event_in_place(working, event, self.registry)
                if before is not None:
                    from tinyworld.eval.invariants import check_event

                    violations = check_event(before, event, working)
                    if violations:
                        raise InvariantError("; ".join(str(v) for v in violations))
            except EffectError as exc:
                if atomic:
                    raise CommitError(str(exc)) from exc
                working = backup
                result.rejected.append((draft, str(exc)))
                continue
            result.events.append(event)
            if observe is not None:
                result.observed.append(observe(event, working))

        if result.events:
            self.store.append(result.events)
            before = self.state.seq
            self.state = working
            if working.seq // self.snapshot_every > before // self.snapshot_every:
                self.store.save_snapshot(self.branch_id, working)
        return result

    def fork(self, at_seq: int, name: str) -> "WorldSession":
        branch_id = self.store.fork(self.branch_id, at_seq, name)
        return WorldSession(
            self.store,
            branch_id,
            registry=self.registry,
            snapshot_every=self.snapshot_every,
            debug=self.debug,
        )
