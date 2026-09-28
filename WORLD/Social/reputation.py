class ReputationSystem:
    """
    Manages village-level reputation for NPCs.

    Reputation is different from a relationship:

    - Relationship = how one NPC feels about another NPC.
    - Reputation = how the village generally views an NPC.
    """

    MIN_REPUTATION = -100
    MAX_REPUTATION = 100

    COOPERATION_CHANGE = 5
    CONFLICT_CHANGE = -5

    def increase(self, npc, amount: int) -> None:
        if amount < 0:
            raise ValueError(
                "Reputation increase cannot be negative."
            )

        npc.reputation = min(
            self.MAX_REPUTATION,
            npc.reputation + amount,
        )

    def decrease(self, npc, amount: int) -> None:
        if amount < 0:
            raise ValueError(
                "Reputation decrease cannot be negative."
            )

        npc.reputation = max(
            self.MIN_REPUTATION,
            npc.reputation - amount,
        )

    def apply_cooperation(self, npc) -> None:
        self.increase(
            npc,
            self.COOPERATION_CHANGE,
        )

    def apply_conflict(self, npc) -> None:
        self.decrease(
            npc,
            abs(self.CONFLICT_CHANGE),
        )