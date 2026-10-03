from WORLD.AI.action import ActionType
from WORLD.Economy.trading import buy_food
from WORLD.Events.event import WorldEvent
from WORLD.Social.social import SocialSystem
from WORLD.Work.work import WorkStatus


class ActionExecutor:
    WORK_ENERGY_COST = 5
    SLEEP_ENERGY_GAIN = 15

    WORK_LOCATIONS = {
        "Village Farm",
        "General Store",
    }

    def execute(
        self,
        npc,
        action: ActionType,
        world,
        target=None,
    ) -> bool:

        event_engine = getattr(world, "event_engine", None)
        if event_engine is not None:
            return event_engine.process_npc_action(
                world,
                npc,
                action,
                target,
            ).success

        if action == ActionType.EAT:
            success = npc.eat()

            if success:
                world.event_log.add(
                    WorldEvent(
                        day=world.clock.day,
                        hour=world.clock.hour,
                        event_type="EAT",
                        actor=npc.name,
                        target=None,
                        description=(
                            f"{npc.name} ate food."
                        ),
                    )
                )

            return success

        if action == ActionType.SLEEP:
            success = self._sleep(npc, world)

            if success:
                world.event_log.add(
                    WorldEvent(
                        day=world.clock.day,
                        hour=world.clock.hour,
                        event_type="SLEEP",
                        actor=npc.name,
                        target=None,
                        description=(
                            f"{npc.name} rested at home."
                        ),
                    )
                )

            return success

        if action == ActionType.WORK:
            success = self._work(npc, world)

            if success:
                world.event_log.add(
                    WorldEvent(
                        day=world.clock.day,
                        hour=world.clock.hour,
                        event_type="WORK",
                        actor=npc.name,
                        target=npc.location,
                        description=(
                            f"{npc.name} worked at "
                            f"{npc.location}."
                        ),
                    )
                )

            return success

        if action == ActionType.SHOP:
            success = self._shop(npc, world)

            if success:
                world.event_log.add(
                    WorldEvent(
                        day=world.clock.day,
                        hour=world.clock.hour,
                        event_type="SHOP",
                        actor=npc.name,
                        target=world.shop.name,
                        description=(
                            f"{npc.name} bought food "
                            f"from {world.shop.name}."
                        ),
                    )
                )

            return success

        if action == ActionType.SOCIALIZE:
            return self._socialize(
                npc,
                world,
                target,
            )

        return False

    def _sleep(self, npc, world=None) -> bool:
        was_at_work = npc.location in self.WORK_LOCATIONS
        was_low_energy = npc.energy <= 30

        if npc.location != npc.home:
            npc.move_to(npc.home)

        old_energy = npc.energy

        npc.restore_energy(
            self.SLEEP_ENERGY_GAIN
        )

        success = npc.energy > old_energy

        if (
            success
            and was_at_work
            and was_low_energy
            and world is not None
            and hasattr(world, "work_status")
        ):
            world.work_status[npc.name] = WorkStatus.TOO_TIRED

        return success

    def _work(self, npc, world=None) -> bool:
        if npc.location not in self.WORK_LOCATIONS:
            return False

        old_energy = npc.energy

        npc.use_energy(
            self.WORK_ENERGY_COST
        )

        success = npc.energy < old_energy

        if success and world is not None:
            if hasattr(world, "work_status"):
                world.work_status[npc.name] = WorkStatus.WORKED

        return success

    def _shop(self, npc, world) -> bool:
        npc.move_to(world.shop.name)

        return buy_food(
            npc,
            world.shop,
        )

    def _socialize(
        self,
        npc,
        world,
        target=None,
    ) -> bool:

        social_system = SocialSystem()

        if target is not None:
            if target is npc:
                return False

            if target.location != npc.location:
                return False

            social_system.interact(
                npc,
                target,
                world,
            )

            return True

        for other in world.npcs:
            if other is npc:
                continue

            if other.location != npc.location:
                continue

            social_system.interact(
                npc,
                other,
                world,
            )

            return True

        return False