from WORLD.Events.event import WorldEvent


class EventLog:
    """
    Stores world events in chronological order.
    """

    def __init__(self) -> None:
        self.events: list[WorldEvent] = []

    def add(self, event: WorldEvent) -> None:
        self.events.append(event)

    def recent(self, limit: int = 20) -> list[WorldEvent]:
        if limit < 0:
            raise ValueError("limit cannot be negative")

        if limit == 0:
            return []

        return self.events[-limit:]