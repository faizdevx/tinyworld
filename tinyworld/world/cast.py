"""A cast library: people who can reappear in later worlds, with their history.

Saving a person stores what makes them who they are (their persona, age and
trade, what they own, who they were close to) and a short account of their life
from their own memories. Loading one into another world creates them there as a
person with that persona and the account as backstory, so they remember a life
from before.
"""

import json
import time

from tinyworld.agents.persona import persona_of
from tinyworld.core import effects as fx
from tinyworld.core.events import EventDraft
from tinyworld.core.state import Entity, WorldState
from tinyworld.core.store import Store

SCHEMA = """
CREATE TABLE IF NOT EXISTS cast_library (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    saved_at REAL NOT NULL,
    body TEXT NOT NULL
)
"""


class CastLibrary:
    def __init__(self, store: Store) -> None:
        self.store = store
        store.execute(SCHEMA)

    def save(self, sim, person_id: str, note: str = "") -> str:
        """Put a person in the library; returns their cast id."""
        session = sim.session
        state = session.state
        person = state.entities[person_id]
        persona = persona_of(person)
        memories = sim.memory.list(session.branch_id, person_id, kinds=("summary", "reflection", "observation"))
        important = sorted(memories, key=lambda m: -m.importance)[:8]
        story = " ".join(m.text for m in sorted(important, key=lambda m: m.created_seq))
        body = {
            "name": person.name,
            "age": person.attrs.get("age"),
            "occupation": person.attrs.get("occupation", ""),
            "persona": persona.model_dump() if persona else None,
            "backstory": (note + " " + story).strip(),
            "from_world": session.world_id,
            "saved_at_world_time": state.sim_time.isoformat(),
            "spouse": state.entities[person.attrs["spouse"]].name if person.attrs.get("spouse") in state.entities else None,
            "children": [c.name for c in state.people(alive=False) if person_id in (c.attrs.get("parents") or [])],
        }
        cast_id = "cast_" + person_id.split(":")[1]
        self.store.execute(
            "INSERT OR REPLACE INTO cast_library VALUES (?,?,?,?)", (cast_id, person.name, time.time(), json.dumps(body))
        )
        return cast_id

    def all(self) -> list[dict]:
        return [{"id": r["id"], "name": r["name"]} for r in self.store.query("SELECT id, name FROM cast_library ORDER BY name")]

    def get(self, cast_id: str) -> dict | None:
        rows = self.store.query("SELECT body FROM cast_library WHERE id=?", (cast_id,))
        return json.loads(rows[0]["body"]) if rows else None

    def appear(self, state: WorldState, cast_id: str, place: str) -> tuple[EventDraft, list[tuple[str, str]]]:
        """Drafts that bring a saved person into this world at ``place``, and their backstory as a memory."""
        from tinyworld.core.ids import make_id

        body = self.get(cast_id)
        if body is None:
            raise KeyError(cast_id)
        pid = make_id("person", body["name"])
        if pid in state.entities:
            raise ValueError(f"{body['name']} is already here")
        attrs = {"tier": 0, "occupation": body.get("occupation") or ""}
        if isinstance(body.get("age"), int):
            attrs["age"] = body["age"]
        if body.get("persona"):
            attrs["persona"] = body["persona"]
        person = Entity(id=pid, kind="person", name=body["name"], location=place, attrs=attrs)
        draft = EventDraft(
            kind="system", actor="system", location=place, visibility="public",
            effects=[fx.CreateEntity(entity=person)],
            narration=f"{body['name']} arrives, with a life behind them.",
        )
        story = body.get("backstory") or ""
        notes = [(pid, "My life so far: " + story)] if story else []
        return draft, notes
