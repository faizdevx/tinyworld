from WORLD.Events.event import WorldEvent
from WORLD.Events.event import EventProposal, EventSource


class RestockingSystem:
    RESTOCK_HOUR = 13
    RESTOCK_AMOUNT = 5

    def update(self, world) -> None:
        if world.clock.hour != self.RESTOCK_HOUR:
            return

        if world.food.quantity < self.RESTOCK_AMOUNT:
            return

        event_engine = getattr(world, "event_engine", None)
        if event_engine is not None:
            event_engine.process(
                world,
                EventProposal(
                    actor="system:restocking",
                    action_type="restock",
                    target="resource:Food",
                    properties={"quantity": self.RESTOCK_AMOUNT},
                    source=EventSource.SYSTEM,
                    timestamp=(world.clock.day, world.clock.hour),
                ),
            )
            return

        success = world.food.consume(
            self.RESTOCK_AMOUNT
        )

        if not success:
            return

        world.shop.food += self.RESTOCK_AMOUNT

        world.event_log.add(
            WorldEvent(
                day=world.clock.day,
                hour=world.clock.hour,
                event_type="RESTOCK",
                actor="Village",
                target=world.shop.name,
                description=(
                    f"{world.shop.name} received "
                    f"{self.RESTOCK_AMOUNT} food."
                ),
            )
        )