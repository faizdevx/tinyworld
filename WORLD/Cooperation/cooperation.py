from WORLD.Events.event import WorldEvent
from WORLD.NPCs.memory import Memory


class CooperationSystem:
    HUNGER_THRESHOLD = 70

    BASE_RELATIONSHIP_THRESHOLD = 30
    HIGH_REPUTATION_THRESHOLD = 50
    LOW_REPUTATION_THRESHOLD = -50

    HIGH_REPUTATION_RELATIONSHIP_THRESHOLD = 20
    LOW_REPUTATION_RELATIONSHIP_THRESHOLD = 50

    FOOD_TRANSFER_AMOUNT = 1

    def _required_relationship(self, receiver) -> int:
        if receiver.reputation >= self.HIGH_REPUTATION_THRESHOLD:
            return self.HIGH_REPUTATION_RELATIONSHIP_THRESHOLD

        if receiver.reputation <= self.LOW_REPUTATION_THRESHOLD:
            return self.LOW_REPUTATION_RELATIONSHIP_THRESHOLD

        return self.BASE_RELATIONSHIP_THRESHOLD

    def _needs_help(self, receiver, world) -> bool:
        return (
            receiver.food == 0
            and receiver.hunger >= self.HUNGER_THRESHOLD
            and receiver.money < world.shop.food_price
        )

    def _can_donate(self, donor, receiver) -> bool:
        if donor is receiver:
            return False

        if donor.location != receiver.location:
            return False

        if donor.food < self.FOOD_TRANSFER_AMOUNT:
            return False

        required_relationship = self._required_relationship(receiver)

        return (
            receiver.get_relationship(donor)
            >= required_relationship
        )

    def _transfer_food(self, donor, receiver) -> bool:
        if not donor.consume_food(self.FOOD_TRANSFER_AMOUNT):
            return False

        receiver.add_food(self.FOOD_TRANSFER_AMOUNT)
        return True

    def update(self, world) -> None:
        for receiver in world.npcs:
            if not self._needs_help(receiver, world):
                continue

            donors = [
                npc
                for npc in world.npcs
                if self._can_donate(npc, receiver)
            ]

            if not donors:
                continue

            donor = donors[0]

            if not self._transfer_food(donor, receiver):
                continue

            donor.change_relationship(receiver, 1)
            receiver.change_relationship(donor, 1)

            donor.remember(
                Memory(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event=f"Gave food to {receiver.name}",
                    importance=2,
                )
            )

            receiver.remember(
                Memory(
                    day=world.clock.day,
                    hour=world.clock.hour,
                    event=f"Received food from {donor.name}",
                    importance=2,
                )
            )

            donor.reputation = min(
                donor.reputation + 5,
                100,
            )

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