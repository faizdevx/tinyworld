from WORLD.AI.action import ActionType
from WORLD.AI.goal import GoalType
from WORLD.AI.plans import Plan


class PlanExecutor:
    HUNGER_INTERRUPT_THRESHOLD = 95

    ACTION_MAP = {
        "eat": ActionType.EAT,
        "sleep": ActionType.SLEEP,
        "work": ActionType.WORK,
        "shop": ActionType.SHOP,
        "buy_food": ActionType.SHOP,
        "socialize": ActionType.SOCIALIZE,
    }

    def __init__(self, action_executor):
        self.action_executor = action_executor

    def should_interrupt(self, npc, plan: Plan) -> bool:
        if plan.is_complete():
            return False

        if plan.is_interrupted():
            return True

        if npc.hunger >= self.HUNGER_INTERRUPT_THRESHOLD:
            return plan.goal_type not in {
                GoalType.SATISFY_HUNGER,
                GoalType.SURVIVE,
            }

        return False

    def interrupt_if_needed(self, npc, plan: Plan) -> bool:
        if not self.should_interrupt(npc, plan):
            return False

        plan.interrupt()
        return True

    def execute_current_step(self, npc, plan: Plan, world) -> bool:
        if plan.is_complete() or plan.is_interrupted():
            return False

        if self.interrupt_if_needed(npc, plan):
            return False

        step = plan.current_action()

        if step not in self.ACTION_MAP:
            return False

        action_type = self.ACTION_MAP[step]

        success = self.action_executor.execute(
            npc,
            action_type,
            world,
        )

        if not success:
            return False

        plan.advance()
        return True