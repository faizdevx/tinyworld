from WORLD.Events.event import WorldEvent


class EnvironmentSystem:
    NORMAL_PRODUCTION_MULTIPLIER = 1.0
    DROUGHT_PRODUCTION_MULTIPLIER = 0.5

    DAILY_CHECK_HOUR = 8

    # 25% chance:
    # False, False, False, True
    DROUGHT_ROLL = (
        False,
        False,
        False,
        True,
    )

    def __init__(self, random_events_enabled: bool = False):
        self.drought_active = False
        self.random_events_enabled = random_events_enabled

    def start_drought(self, world) -> None:
        if self.drought_active:
            return

        self.drought_active = True

        world.event_log.add(
            WorldEvent(
                day=world.clock.day,
                hour=world.clock.hour,
                event_type="DROUGHT_STARTED",
                actor="Environment",
                target="Village Farm",
                description="A drought reduced farm production.",
            )
        )

    def end_drought(self, world) -> None:
        if not self.drought_active:
            return

        self.drought_active = False

        world.event_log.add(
            WorldEvent(
                day=world.clock.day,
                hour=world.clock.hour,
                event_type="DROUGHT_ENDED",
                actor="Environment",
                target="Village Farm",
                description="The drought ended and farm production recovered.",
            )
        )

    def production_multiplier(self) -> float:
        if self.drought_active:
            return self.DROUGHT_PRODUCTION_MULTIPLIER

        return self.NORMAL_PRODUCTION_MULTIPLIER

    def update(self, world) -> None:
        if not self.random_events_enabled:
            return

        if world.clock.hour != self.DAILY_CHECK_HOUR:
            return

        if self.drought_active:
            self.end_drought(world)
            return

        should_start = world.rng.choice(self.DROUGHT_ROLL)

        if should_start:
            self.start_drought(world)