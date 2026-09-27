from WORLD.Economy.trading import buy_food


class ShoppingSystem:
    SHOPPING_HOUR = 19
    SHOP_LOCATION = "General Store"

    def update(self, world) -> None:
        # Shopping happens at 19:00.
        if world.clock.hour != self.SHOPPING_HOUR:
            return

        for npc in world.npcs:

            # Shopkeepers do not buy from their own shop.
            if npc.role == "shopkeeper":
                continue

            # NPC only buys if they have no food.
            if npc.food > 0:
                continue

            # NPC goes to the shop.
            npc.move_to(self.SHOP_LOCATION)

            # NPC attempts to buy one food.
            buy_food(npc, world.shop)