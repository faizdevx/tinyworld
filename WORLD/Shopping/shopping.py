from WORLD.AI.action import ActionType


class ShoppingSystem:
    def update(self, world) -> None:
        for npc in world.npcs:
            if npc.role == "shopkeeper":
                continue

            decision = world.decision_system.decide(
                npc,
                world,
            )

            if decision.chosen_action != ActionType.SHOP:
                continue

            world.action_executor.execute(
                npc,
                ActionType.SHOP,
                world,
            )