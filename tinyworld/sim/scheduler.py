"""How much time one tick covers: short while things happen, long while they do not."""

from dataclasses import dataclass

from tinyworld.core import effects as fx
from tinyworld.core.events import Event
from tinyworld.core.state import WorldState


@dataclass
class StepPolicy:
    min_minutes: int = 30
    base_minutes: int = 60
    max_minutes: int = 480
    night_start: int = 23
    night_end: int = 5

    def _is_night(self, state: WorldState) -> bool:
        hour = state.sim_time.hour
        return hour >= self.night_start or hour < self.night_end

    @staticmethod
    def _gathered(state: WorldState) -> bool:
        """Two or more deciding agents share a place."""
        seen: set[str] = set()
        for person in state.people():
            if person.attrs.get("tier", 0) != 0 or not person.location:
                continue
            if person.location in seen:
                return True
            seen.add(person.location)
        return False

    @staticmethod
    def activity(events: list[Event]) -> str:
        """How lively the last tick was: "talk", "action" or "quiet"."""
        acted = [e for e in events if e.actor.startswith("person:")]
        if any(isinstance(x, fx.Utter) for e in acted for x in e.effects):
            return "talk"
        if any(e.effects for e in acted) or any(e.kind == "god" for e in events):
            return "action"
        return "quiet"

    def next_step(
        self,
        state: WorldState,
        last_events: list[Event],
        last_step: int | None = None,
        *,
        lengthen: bool = False,
    ) -> int:
        activity = self.activity(last_events)
        if activity == "talk" and self._gathered(state):
            step = self.min_minutes
        elif activity == "quiet":
            if self._is_night(state):
                step = self.max_minutes
            else:
                step = min(self.max_minutes, (last_step or self.base_minutes) * 2)
        else:
            step = self.base_minutes
        if lengthen:
            step = min(self.max_minutes, step * 2)
        return step
