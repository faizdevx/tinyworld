from WORLD.AI.action import ActionType


class WorkSystem:
    WORK_LOCATIONS = {
        "Village Farm",
        "General Store",
    }

    def update(self, world) -> None:
        for npc in world.npcs:

            if npc.location not in self.WORK_LOCATIONS:
                continue

            decision = world.decision_system.decide(npc, world)

            if decision.chosen_action == ActionType.WORK:
                world.action_executor.execute(
                    npc,
                    ActionType.WORK,
                    world,
                )

            elif decision.chosen_action == ActionType.SLEEP:
                world.action_executor.execute(
                    npc,
                    ActionType.SLEEP,
                    world,
                )