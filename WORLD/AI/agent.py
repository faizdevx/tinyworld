from WORLD.AI.decision import DecisionSystem


class AgentSystem:
    def __init__(
        self,
        decision_system: DecisionSystem,
    ) -> None:
        self.decision_system = decision_system

    def update(self, world) -> None:
        for npc in world.npcs:
            decision = self.decision_system.decide(
                npc,
                world,
            )

            world.action_executor.execute(
                npc,
                decision.chosen_action,
                world,
            )