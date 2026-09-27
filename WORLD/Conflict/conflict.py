from WORLD.Events.event import WorldEvent
from WORLD.NPCs.memory import Memory


class ConflictSystem:
    """
    Handles simple conflicts caused by food scarcity.

    A conflict occurs when:
    - shop food is critically low
    - two NPCs are in the same location
    - both NPCs are hungry
    - neither NPC can currently afford food
    """

    FOOD_SCARCITY_THRESHOLD = 2
    HUNGER_THRESHOLD = 70
    RELATIONSHIP_CHANGE = -5

    def update(self, world) -> None:
        if world.shop.food > self.FOOD_SCARCITY_THRESHOLD:
            return

        conflicted_pairs: set[tuple[str, str]] = set()

        for npc_a in world.npcs:
            if not self._needs_food(npc_a, world):
                continue

            for npc_b in world.npcs:
                if npc_b is npc_a:
                    continue

                if not self._needs_food(npc_b, world):
                    continue

                if npc_a.location != npc_b.location:
                    continue

                pair = tuple(
                    sorted((npc_a.name, npc_b.name))
                )

                if pair in conflicted_pairs:
                    continue

                self._create_conflict(
                    npc_a,
                    npc_b,
                    world,
                )

                conflicted_pairs.add(pair)

    def _needs_food(self, npc, world) -> bool:
        """
        Return True when an NPC is currently struggling
        to obtain food.
        """

        if npc.hunger < self.HUNGER_THRESHOLD:
            return False

        if npc.food > 0:
            return False

        if npc.money >= world.shop.food_price:
            return False

        return True

    def _create_conflict(
        self,
        npc_a,
        npc_b,
        world,
    ) -> None:
        """
        Apply the consequences of a food-related conflict.
        """

        npc_a.change_relationship(
            npc_b,
            self.RELATIONSHIP_CHANGE,
        )

        npc_b.change_relationship(
            npc_a,
            self.RELATIONSHIP_CHANGE,
        )

        npc_a.remember(
            Memory(
                day=world.clock.day,
                hour=world.clock.hour,
                event=f"Argued with {npc_b.name}",
                importance=2,
            )
        )

        npc_b.remember(
            Memory(
                day=world.clock.day,
                hour=world.clock.hour,
                event=f"Argued with {npc_a.name}",
                importance=2,
            )
        )

        world.event_log.add(
            WorldEvent(
                day=world.clock.day,
                hour=world.clock.hour,
                event_type="CONFLICT",
                actor=npc_a.name,
                target=npc_b.name,
                description=(
                    f"{npc_a.name} argued with "
                    f"{npc_b.name} over scarce food."
                ),
            )
        )