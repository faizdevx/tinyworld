from WORLD.NPCs.npc import NPC


class ScheduleSystem:

    def update_npc(self, npc: NPC, hour: int) -> None:
        if not 0 <= hour <= 23:
            raise ValueError("Hour must be between 0 and 23.")

        destination = npc.schedule.get(hour)

        if destination is None:
            destination = npc.home

        npc.move_to(destination)