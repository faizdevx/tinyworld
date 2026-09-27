class RestockingSystem:
    RESTOCK_HOUR = 13
    RESTOCK_AMOUNT = 5

    def update(self, world) -> None:
        # Restocking happens only at 13:00.
        if world.clock.hour != self.RESTOCK_HOUR:
            return

        # There must be enough food in village storage.
        if world.food.quantity < self.RESTOCK_AMOUNT:
            return

        # Move food from village storage to the shop.
        success = world.food.consume(self.RESTOCK_AMOUNT)

        if not success:
            return

        world.shop.food += self.RESTOCK_AMOUNT