"""Branch helpers: forking, ancestry and comparison."""

from dataclasses import dataclass

from tinyworld.core.events import Event
from tinyworld.core.store import Store


@dataclass(frozen=True)
class BranchInfo:
    id: str
    world_id: str
    parent_id: str | None
    fork_seq: int | None
    name: str
    head_seq: int


def info(store: Store, branch_id: str) -> BranchInfo:
    row = store.branch(branch_id)
    return BranchInfo(
        id=row["id"],
        world_id=row["world_id"],
        parent_id=row["parent_id"],
        fork_seq=row["fork_seq"],
        name=row["name"],
        head_seq=store.head_seq(branch_id),
    )


def tree(store: Store, world_id: str) -> list[BranchInfo]:
    return [info(store, row["id"]) for row in store.branches(world_id)]


def fork(store: Store, branch_id: str, at_seq: int, name: str) -> str:
    return store.fork(branch_id, at_seq, name)


def ancestors(store: Store, branch_id: str) -> list[str]:
    """Root-first branch ids, ending with ``branch_id``."""
    return [ancestor for ancestor, _ in store.lineage(branch_id)]


def common_seq(store: Store, first: str, second: str) -> int:
    """The last sequence number the two branches share."""
    limits_first = dict(store.lineage(first))
    limits_second = dict(store.lineage(second))
    shared = [b for b in limits_first if b in limits_second]
    if not shared:
        return 0
    last = shared[-1]
    candidates = [
        limit
        for limit in (limits_first[last], limits_second[last])
        if limit is not None
    ]
    if candidates:
        return min(candidates)
    return store.head_seq(last)


def diverging_events(
    store: Store, first: str, second: str
) -> tuple[int, list[Event], list[Event]]:
    """Events on each branch after the point where they split."""
    split = common_seq(store, first, second)
    return (
        split,
        store.events(first, after=split),
        store.events(second, after=split),
    )
