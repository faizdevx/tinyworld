from WORLD.world import World
from WORLD.Genesis.scenario import WorldScenario


class WorldGenerator:
    """
    Converts a declarative scenario into a concrete World.

    The Genesis layer creates initial state; the Simulation layer
    mutates the world after creation.
    """

    def generate(
        self,
        scenario: WorldScenario,
        *,
        seed: int = 42,
    ) -> World:
        world = World(seed=seed)
        self._apply_resources(world, scenario)
        self._apply_buildings(world, scenario)
        return world

    def _apply_resources(self, world, scenario: WorldScenario) -> None:
        if "Food" in scenario.resources:
            world.food.quantity = scenario.resources["Food"]

    def _apply_buildings(self, world, scenario: WorldScenario) -> None:
        # Genesis 9.1 intentionally keeps building generation minimal.
        # The building list is recorded declaratively in the scenario;
        # actual building creation remains a later generation step.
        _ = (world, scenario)
