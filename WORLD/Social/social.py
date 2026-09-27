from itertools import combinations

from WORLD.AI.action import ActionType
from WORLD.NPCs.memory import Memory


class SocialSystem:
    def update(self, world) -> None:
        interacted_pairs: set[tuple[str, str]] = set()

        for npc in world.npcs:

            decision = world.decision_system.decide(
                npc,
                world,
            )

            if decision.chosen_action != ActionType.SOCIALIZE:
                continue

            for other in world.npcs:
                if other is npc:
                    continue

                if other.location != npc.location:
                    continue

                pair = tuple(
                    sorted((npc.name, other.name))
                )

                if pair in interacted_pairs:
                    continue

                success = world.action_executor.execute(
                    npc,
                    ActionType.SOCIALIZE,
                    world,
                    target=other,
                )

                if success:
                    interacted_pairs.add(pair)

                break

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