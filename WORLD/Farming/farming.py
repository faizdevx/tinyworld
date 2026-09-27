from WORLD.Events.event import WorldEvent
from WORLD.Work.work import WorkStatus


class FarmingSystem:
    FOOD_PER_FARMER = 2
    HARVEST_HOUR = 12
    FARM_LOCATION = "Village Farm"

    def update(self, world) -> None:
        if world.clock.hour != self.HARVEST_HOUR:
            return

        farmers = [
            npc
            for npc in world.npcs
            if npc.role == "farmer"
            and npc.location == self.FARM_LOCATION
        ]

        production = 0

        for npc in farmers:

            # -------------------------------------------------
            # Work attendance
            #
            # If this farmer has an explicit work status,
            # use it to determine whether they produced food.
            #
            # If no status exists, preserve the original
            # farming behavior and use productivity.
            # -------------------------------------------------

            if hasattr(world, "work_status"):
                status = world.work_status.get(npc.name)

                if status is not None:
                    if status != WorkStatus.WORKED:
                        continue

            # -------------------------------------------------
            # Productivity
            # -------------------------------------------------

            production += int(
                self.FOOD_PER_FARMER
                * npc.productivity
            )

        # No production means no harvest event.
        if production == 0:
            return

        world.food.add(production)

        # -----------------------------------------------------
        # Record harvest event
        # -----------------------------------------------------

        if hasattr(world, "event_log"):
            world.event_log.add(
                WorldEvent(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event_type="HARVEST",
                    actor="Village",
                    target=None,
                    description=(
                        f"Farmers produced "
                        f"{production} food."
                    ),
                )
            )