from enum import Enum
from abc import ABC, abstractmethod


class ActionType(Enum):
    EAT = "eat"
    SLEEP = "sleep"
    WORK = "work"
    SHOP = "shop"
    SOCIALIZE = "socialize"
    GO_TO_WORK = "go_to_work"
    FIND_FOOD = "find_food"
    OBTAIN_FOOD = "obtain_food"
    GO_HOME = "go_home"
    FIND_FAMILY = "find_family"
    HELP_FAMILY = "help_family"
    MAINTAIN_HOME = "maintain_home"




class Action(ABC):
    @abstractmethod
    def can_execute(self, npc, world) -> bool:
        pass

    @abstractmethod
    def execute(self, npc, world) -> bool:
        pass


class BuyFoodAction(Action):
    def can_execute(self, npc, world) -> bool:
        return (
            npc.location == world.shop.name
            and npc.money >= world.shop.food_price
            and world.shop.food > 0
        )

    def execute(self, npc, world) -> bool:
        if not self.can_execute(npc, world):
            return False

        price = world.shop.food_price

        npc.money -= price
        world.shop.money += price
        world.shop.food -= 1
        npc.food += 1

        return True
