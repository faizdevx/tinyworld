from WORLD.Events.event import WorldEvent
from WORLD.NPCs.memory import Memory


class CooperationSystem:
    """
    Handles food sharing between nearby NPCs.

    A hungry NPC can receive one food unit from another NPC
    when the donor and receiver satisfy the cooperation rules.
    """

    HUNGER_THRESHOLD = 70
    RELATIONSHIP_THRESHOLD = 30
    FOOD_TRANSFER_AMOUNT = 1

    def update(self, world) -> None:
        for receiver in world.npcs:
            if not self._needs_help(receiver, world):
                continue

            donor = self._find_donor(
                receiver,
                world,
            )

            if donor is None:
                continue

            self._transfer_food(
                donor,
                receiver,
                world,
            )

    def _needs_help(self, npc, world) -> bool:
        """
        Return True when an NPC needs food assistance.
        """

        if npc.food > 0:
            return False

        if npc.hunger < self.HUNGER_THRESHOLD:
            return False

        if npc.money >= world.shop.food_price:
            return False

        return True

    def _find_donor(self, receiver, world):
        """
        Find the first nearby NPC who can donate food.
        """

        for donor in world.npcs:
            if donor is receiver:
                continue

            if donor.location != receiver.location:
                continue

            if donor.food < self.FOOD_TRANSFER_AMOUNT:
                continue

            relationship = receiver.get_relationship(
                donor
            )

            if relationship < self.RELATIONSHIP_THRESHOLD:
                continue

            return donor

        return None

    def _transfer_food(
        self,
        donor,
        receiver,
        world,
    ) -> bool:
        """
        Transfer food from donor to receiver.

        Successful cooperation:
        - transfers food
        - improves relationship
        - creates memories
        - increases donor reputation
        - creates a world event
        """

        success = donor.consume_food(
            self.FOOD_TRANSFER_AMOUNT
        )

        if not success:
            return False

        receiver.add_food(
            self.FOOD_TRANSFER_AMOUNT
        )

        # Relationship changes.
        donor.change_relationship(
            receiver,
            1,
        )

        receiver.change_relationship(
            donor,
            1,
        )

        # Memories.
        donor.remember(
            Memory(
                day=world.clock.day,
                hour=world.clock.hour,
                event=(
                    f"Gave food to {receiver.name}"
                ),
                importance=2,
            )
        )

        receiver.remember(
            Memory(
                day=world.clock.day,
                hour=world.clock.hour,
                event=(
                    f"Received food from {donor.name}"
                ),
                importance=2,
            )
        )

        # Reputation.
        world.reputation_system.apply_cooperation(
            donor
        )

        # World event.
        world.event_log.add(
            WorldEvent(
                day=world.clock.day,
                hour=world.clock.hour,
                event_type="FOOD_GIFT",
                actor=donor.name,
                target=receiver.name,
                description=(
                    f"{donor.name} gave food to "
                    f"{receiver.name}."
                ),
            )
        )

        return True