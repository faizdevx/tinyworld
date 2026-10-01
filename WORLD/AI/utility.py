from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from dataclasses import dataclass

@dataclass

class UtilityContext:
    social_need: float = 0.0
    money_need: float = 0.0
    relationship_strength: float = 0.0

class UtilitySystem:
    """
    Converts world/context needs into utility scores while
    incorporating NPC personality.
    """

    def score_socialize(self, npc, context: UtilityContext) -> float:
        return (
            context.social_need
            * npc.personality.sociability
        )

    def experience_social_modifier(
        self,
        knowledge,
        target,
    ) -> int:
        modifier = 0
        for fact in knowledge:
            if fact.subject != target:
                continue
            if fact.predicate != "provides_help":
                continue
            if fact.value is True:
                modifier += 20
            elif fact.value is False:
                modifier -= 20
        return modifier

    def score_socialize_with_experience(
        self,
        npc,
        context: UtilityContext,
        target: str,
    ) -> float:
        score = self.score_socialize(npc, context)
        knowledge = getattr(npc, "knowledge", None)
        if knowledge is None:
            return score
        score += self.experience_social_modifier(
            knowledge.for_subject(target),
            target,
        )
        return score

    def score_work(self, npc, context: UtilityContext) -> float:
        return (
            context.money_need
            * npc.personality.ambition
        )

    def score_helping(self, npc, context: UtilityContext) -> float:
        return (
            context.relationship_strength
            * npc.personality.generosity
        )

WORK_LOCATIONS = {
    "Village Farm",
    "General Store",
}


def _schedule_destination(npc, world):
    """
    Return the NPC's explicit scheduled destination
    for the current hour.

    If there is no schedule entry, return None.
    """
    return npc.schedule.get(world.clock.hour)


def _has_social_memory(npc, world) -> bool:
    """
    Return True if the NPC has a memory related to
    social interaction.
    """
    for memory in npc.memories:
        event = memory.event.lower()

        if (
            "social" in event
            or "spent time" in event
            or "interact" in event
            or "talk" in event
            or "conversation" in event
        ):
            return True

    return False


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

        score = 10
        score += max(best_relationship, 0) // 5

        if _has_social_memory(npc, world):
            score += 5

    else:
        return 0

    # ---------------------------------------------------------
    # Goal influence
    # ---------------------------------------------------------

    if GoalType.SATISFY_HUNGER in goals:
        if action in {
            ActionType.EAT,
            ActionType.SHOP,
        }:
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

    # ---------------------------------------------------------
    # Schedule influence
    # ---------------------------------------------------------

    scheduled_destination = _schedule_destination(
        npc,
        world,
    )

    if scheduled_destination is not None:

        if scheduled_destination == npc.location:

            if action == ActionType.WORK:
                score += 15

            elif action == ActionType.SOCIALIZE:
                score += 5

        if scheduled_destination == npc.home:
            if action == ActionType.SLEEP:
                score += 10

        if scheduled_destination == world.shop.name:
            if action == ActionType.SHOP:
                score += 10

    return score