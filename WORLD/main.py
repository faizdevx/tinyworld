from WORLD.Village.village import Village
from WORLD.Simulation.simulation import Simulation


def main() -> None:
    world = Village().create()
    simulation = Simulation(world)

    for _ in range(24):

        # Remember which hour we are processing.
        current_time = world.clock.time_string()

        # Run the simulation for this hour.
        simulation.tick()

        # Show the state after this hour was processed.
        print()
        print("========================")
        print(current_time)
        print("========================")

        for npc in world.npcs:
            print(
                f"{npc.name:8}"
                f" | {npc.role:12}"
                f" | {npc.location:15}"
                f" | energy={npc.energy:3}"
                f" | food={npc.food:2}"
                f" | money={npc.money:3}"
            )

        print()
        print(f"Village food : {world.food.quantity}")
        print(f"Shop food    : {world.shop.food}")
        print(f"Shop money   : {world.shop.money}")


if __name__ == "__main__":
    main()