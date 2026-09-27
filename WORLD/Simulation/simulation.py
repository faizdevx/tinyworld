from WORLD.world import World
from WORLD.Work.work import WorkStatus


class Simulation:
    def __init__(self, world: World) -> None:
        self.world = world

    def tick(self) -> None:
        hour = self.world.clock.hour

        # -----------------------------------------------------
        # Reset work attendance for this hour.
        # Everyone starts as absent.
        # Successful work changes the status to WORKED.
        # Sleeping at work because of low energy becomes
        # TOO_TIRED.
        # -----------------------------------------------------

        self.world.work_status = {
            npc.name: WorkStatus.ABSENT
            for npc in self.world.npcs
        }

        # -----------------------------------------------------
        # 1. Follow the normal schedule.
        # -----------------------------------------------------

        for npc in self.world.npcs:
            self.world.schedule_system.update_npc(
                npc,
                hour,
            )

        # -----------------------------------------------------
        # 2. Increase hunger.
        # -----------------------------------------------------

        self.world.needs_system.update_before_decision(
            self.world
        )

        # -----------------------------------------------------
        # 3. Restock food when required.
        # -----------------------------------------------------

        self.world.restocking_system.update(
            self.world
        )

        # -----------------------------------------------------
        # 4. Update food price from current shop supply.
        # -----------------------------------------------------

        if hasattr(self.world, "pricing_system"):
            self.world.pricing_system.update(
                self.world
            )

        # -----------------------------------------------------
        # 5. Each NPC makes exactly one decision.
        # -----------------------------------------------------

        self.world.agent_system.update(
            self.world
        )

        # -----------------------------------------------------
        # 6. Hungry NPCs may receive help from nearby friends.
        # -----------------------------------------------------

        if hasattr(self.world, "cooperation_system"):
            self.world.cooperation_system.update(
                self.world
            )

        # -----------------------------------------------------
        # 7. Food scarcity can create social conflict.
        # -----------------------------------------------------

        if hasattr(self.world, "conflict_system"):
            self.world.conflict_system.update(
                self.world
            )

        # -----------------------------------------------------
        # 8. Farming uses actual work attendance.
        # -----------------------------------------------------

        self.world.farming_system.update(
            self.world
        )

        # -----------------------------------------------------
        # 9. Apply consequences of remaining hunger.
        # -----------------------------------------------------

        self.world.needs_system.update_after_action(
            self.world
        )

        # -----------------------------------------------------
        # 10. Advance time.
        # -----------------------------------------------------

        self.world.clock.tick()

    def run(self, ticks: int) -> None:
        if ticks < 0:
            raise ValueError(
                "ticks cannot be negative"
            )

        for _ in range(ticks):
            self.tick()