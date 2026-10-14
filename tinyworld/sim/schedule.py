"""Events queued for a future moment. Branch-aware like everything else."""

from datetime import datetime

from tinyworld.core.events import EventDraft
from tinyworld.core.store import Store


class Scheduler:
    def __init__(self, store: Store) -> None:
        self.store = store

    def add(
        self, branch_id: str, created_seq: int, due: datetime, draft: EventDraft
    ) -> str:
        count = self.store.query(
            "SELECT COUNT(*) AS n FROM scheduled WHERE branch_id=? AND created_seq=?",
            (branch_id, created_seq),
        )[0]["n"]
        scheduled_id = f"{branch_id}:{created_seq}:{count}"
        self.store.execute(
            "INSERT INTO scheduled VALUES (?,?,?,?,?)",
            (scheduled_id, branch_id, created_seq, due.isoformat(), draft.model_dump_json()),
        )
        return scheduled_id

    def pending(
        self, branch_id: str, *, due_by: datetime | None = None
    ) -> list[tuple[str, datetime, EventDraft]]:
        """Queued events not yet fired on this branch, soonest first."""
        visible, params = self.store.lineage_clause(branch_id, "created_seq")
        done, done_params = self.store.lineage_clause(branch_id, "at_seq")
        sql = (
            f"SELECT * FROM scheduled WHERE {visible} AND id NOT IN"
            f" (SELECT scheduled_id FROM scheduled_done WHERE {done})"
        )
        params += done_params
        if due_by is not None:
            sql += " AND due_time<=?"
            params.append(due_by.isoformat())
        sql += " ORDER BY due_time, id"
        return [
            (
                row["id"],
                datetime.fromisoformat(row["due_time"]),
                EventDraft.model_validate_json(row["draft_json"]),
            )
            for row in self.store.query(sql, params)
        ]

    def mark_done(self, branch_id: str, scheduled_ids: list[str], at_seq: int) -> None:
        self.store.executemany(
            "INSERT OR REPLACE INTO scheduled_done VALUES (?,?,?)",
            [(branch_id, scheduled_id, at_seq) for scheduled_id in scheduled_ids],
        )
