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
        score = 10

        # Only useful when another NPC is nearby.
        has_other_npc = any(
            other is not npc
            and other.location == npc.location
            for other in world.npcs
        )

        if not has_other_npc:
            return 0

    else:
        return 0

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