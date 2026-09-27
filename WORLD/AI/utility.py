from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType


WORK_LOCATIONS = {
    "Village Farm",
    "General Store",
}


def score_action(
    npc,
    action: ActionType,
    world,
    goals: list[GoalType],
) -> int:

    # ---------------------------------------------------------
    # Base score from current NPC state
    # ---------------------------------------------------------

    if action == ActionType.EAT:
        if npc.food <= 0:
            return 0

        score = npc.hunger

    elif action == ActionType.SLEEP:
        score = 100 - npc.energy

    elif action == ActionType.WORK:
        if npc.location not in WORK_LOCATIONS:
            return 0

        score = npc.energy

    elif action == ActionType.SHOP:
        if npc.money < world.shop.food_price:
            return 0

        if npc.food > 0:
            return 0

        score = npc.hunger

    elif action == ActionType.SOCIALIZE:
        nearby_npcs = [
            other
            for other in world.npcs
            if other is not npc
            and other.location == npc.location
        ]

        if not nearby_npcs:
            return 0

        best_relationship = max(
            npc.get_relationship(other)
            for other in nearby_npcs
        )

        score = 10 + max(best_relationship, 0) // 5

    # ---------------------------------------------------------
    # Goal influence
    # ---------------------------------------------------------

    if GoalType.SATISFY_HUNGER in goals:
        if action in {ActionType.EAT, ActionType.SHOP}:
            score += 20

    if GoalType.RESTORE_ENERGY in goals:
        if action == ActionType.SLEEP:
            score += 20

    if GoalType.EARN_MONEY in goals:
        if action == ActionType.WORK:
            score += 20

    if GoalType.SOCIALIZE in goals:
        if action == ActionType.SOCIALIZE:
            score += 20

    return score