class PricingSystem:
    """
    Updates food prices based on the amount of food
    currently available in the shop.
    """

    ABUNDANT_PRICE = 5
    LOW_SUPPLY_PRICE = 6
    CRITICAL_SUPPLY_PRICE = 8

    LOW_SUPPLY_THRESHOLD = 5
    CRITICAL_SUPPLY_THRESHOLD = 2

    def calculate_food_price(self, shop) -> int:
        """
        Calculate the current food price from shop inventory.
        """

        if shop.food <= self.CRITICAL_SUPPLY_THRESHOLD:
            return self.CRITICAL_SUPPLY_PRICE

        if shop.food <= self.LOW_SUPPLY_THRESHOLD:
            return self.LOW_SUPPLY_PRICE

        return self.ABUNDANT_PRICE

    def update(self, world) -> None:
        """
        Update the world's shop food price.
        """

        world.shop.food_price = self.calculate_food_price(
            world.shop
        )