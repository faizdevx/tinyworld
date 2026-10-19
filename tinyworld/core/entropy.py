"""Where the world's chance comes from: the operating system, written down.

Behaviour in v7 is stochastic; storage is a recording. A live run draws from
the operating system's entropy (``secrets``), not from a seed, so two live runs
differ. Every draw that can touch the world is appended to the branch's journal
the moment it is made. A replay builds an ``Entropy`` from that journal and
reads the same draws back in the same order, so a replay of one run is
identical to it.

Nothing else in the code may use ``random`` or ``secrets`` for a choice that
affects the world. ``tests/test_entropy.py`` fails the build if it does.
"""

import json
import secrets
from collections import deque

from tinyworld.core.store import Store

OP = "draw"


class ReplayMismatch(RuntimeError):
    """A replay asked for a draw the recording does not have, or a different one."""


class Entropy:
    """A source of draws bound to one branch's journal."""

    def __init__(self, store: Store | None = None, branch_id: str | None = None,
                 *, recorded: list[dict] | None = None, seq=lambda: 0) -> None:
        self.store = store
        self.branch_id = branch_id
        self._recorded = deque(recorded) if recorded is not None else None
        self._seq = seq
        self._os = secrets.SystemRandom()
        self.draws = 0

    @classmethod
    def replaying(cls, store: Store, source_branch: str, branch_id: str | None = None) -> "Entropy":
        """Serve the draws a finished run made, in order. Records nothing new."""
        recorded = [
            json.loads(row["args_json"]) for row in store.journal(source_branch) if row["op"] == OP
        ]
        return cls(store, branch_id, recorded=recorded)

    @property
    def replay(self) -> bool:
        return self._recorded is not None

    def remaining(self) -> int:
        return len(self._recorded) if self._recorded is not None else 0

    # -- the one primitive ----------------------------------------------

    def _record(self, kind: str, value) -> None:
        if self.store is not None and self.branch_id is not None:
            self.store.journal_add(self.branch_id, self._seq(), OP, {"kind": kind, "value": value})

    def _next(self, kind: str, make):
        """The next value: read from the recording in a replay, made and written down live."""
        self.draws += 1
        if self._recorded is not None:
            if not self._recorded:
                raise ReplayMismatch(f"the recording has no draw left for {kind!r}")
            entry = self._recorded.popleft()
            if entry["kind"] != kind:
                raise ReplayMismatch(f"recorded draw is {entry['kind']!r}, the replay asked for {kind!r}")
            return entry["value"]
        value = make()
        self._record(kind, value)
        return value

    # -- what callers use -----------------------------------------------

    def draw(self, kind: str) -> float:
        """A number in [0, 1)."""
        return self._next(kind, self._os.random)

    def chance(self, kind: str, p: float) -> bool:
        return self.draw(kind) < p

    def randint(self, kind: str, low: int, high: int) -> int:
        """An integer in [low, high], both ends included."""
        return low + min(high - low, int(self.draw(kind) * (high - low + 1)))

    def choice(self, kind: str, options):
        options = list(options)
        if not options:
            raise ValueError("nothing to choose from")
        return options[min(len(options) - 1, int(self.draw(kind) * len(options)))]

    def order(self, kind: str, items):
        """The items in a random order, from one recorded draw per item."""
        keyed = [(self.draw(kind), i, item) for i, item in enumerate(items)]
        return [item for _, _, item in sorted(keyed, key=lambda k: (k[0], k[1]))]


class Fixed(Entropy):
    """Draws from a fixed list, then 0.5. For tests that need a known outcome."""

    def __init__(self, values: list[float] | None = None) -> None:
        super().__init__()
        self._values = deque(values or [])

    def _next(self, kind, make):
        self.draws += 1
        return self._values.popleft() if self._values else 0.5
