from WORLD.world import World
from WORLD.NPCs.npc import NPC
from WORLD.Buildings.buildings import Building


class Village:

    def create(self) -> World:
        world = World()

        self._create_buildings(world)
        self._create_npcs(world)

        return world

    def _create_buildings(self, world: World) -> None:
        world.add_building(
            Building(
                name="Village Farm",
                building_type="farm",
            )
        )

        world.add_building(
            Building(
                name="House 1",
                building_type="house",
            )
        )

        world.add_building(
            Building(
                name="House 2",
                building_type="house",
            )
        )

        world.add_building(
            Building(
                name="Town Hall",
                building_type="town_hall",
            )
        )

    def _create_npcs(self, world: World) -> None:

        rahul = NPC(
            name="Rahul",
            role="farmer",
            money=50,
            home="House 1",
            location="House 1",
            schedule={
                6: "House 1",
                7: "House 1",
                8: "Village Farm",
                9: "Village Farm",
                10: "Village Farm",
                11: "Village Farm",
                12: "Village Farm",
                13: "Village Farm",
                14: "Village Farm",
                15: "Village Farm",
                16: "Village Farm",
                17: "Village Farm",
                18: "House 1",
                19: "General Store",
                20: "House 1",
                21: "House 1",
            },
        )

        arjun = NPC(
            name="Arjun",
            role="farmer",
            money=50,
            home="House 1",
            location="House 1",
            schedule={
                8: "Village Farm",
                9: "Village Farm",
                10: "Village Farm",
                11: "Village Farm",
                12: "Village Farm",
                13: "Village Farm",
                14: "Village Farm",
                15: "Village Farm",
                16: "Village Farm",
                17: "Village Farm",
                19: "General Store",
            },
        )

        ali = NPC(
            name="Ali",
            role="shopkeeper",
            money=50,
            home="House 2",
            location="House 2",
            schedule={
                8: "General Store",
                9: "General Store",
                10: "General Store",
                11: "General Store",
                12: "General Store",
                13: "General Store",
                14: "General Store",
                15: "General Store",
                16: "General Store",
                17: "General Store",
                18: "House 2",
                19: "House 2",
            },
        )

        sara = NPC(
            name="Sara",
            role="worker",
            money=50,
            home="House 1",
            location="House 1",
            schedule={
                8: "Village Farm",
                9: "Village Farm",
                10: "Village Farm",
                11: "Village Farm",
                12: "Village Farm",
                13: "Village Farm",
                14: "Village Farm",
                15: "Village Farm",
                16: "Village Farm",
                17: "Village Farm",
                19: "General Store",
            },
        )

        for npc in (rahul, arjun, sara):
            for hour in (*range(0, 6), *range(19, 24)):
                npc.schedule.setdefault(hour, "General Store")

        world.add_npc(rahul)
        world.add_npc(arjun)
        world.add_npc(ali)
        world.add_npc(sara)