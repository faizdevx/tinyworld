from itertools import combinations

from WORLD.NPCs.memory import Memory


class SocialSystem:
    def update(self, world) -> None:
        for npc_a, npc_b in combinations(world.npcs, 2):
            if npc_a.location != npc_b.location:
                continue

            self.interact(npc_a, npc_b, world)

    def interact(self, npc_a, npc_b, world) -> None:
        npc_a.change_relationship(npc_b, 1)
        npc_b.change_relationship(npc_a, 1)

        npc_a.remember(
            Memory(
                day=world.clock.day,
                hour=world.clock.hour,
                event=f"Spent time with {npc_b.name}",
                importance=1,
            )
        )

        npc_b.remember(
            Memory(
                day=world.clock.day,
                hour=world.clock.hour,
                event=f"Spent time with {npc_a.name}",
                importance=1,
            )
        )