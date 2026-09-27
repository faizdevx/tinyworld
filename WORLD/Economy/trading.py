def buy_food(npc, shop) -> bool:
    # Shop must have food available.
    if shop.food <= 0:
        return False

    # NPC must be able to afford the food.
    if npc.money < shop.food_price:
        return False

    # Move money from NPC to shop.
    npc.money -= shop.food_price
    shop.money += shop.food_price

    # Move one food unit from shop to NPC.
    shop.food -= 1
    npc.food += 1

    return True