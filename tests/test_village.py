from WORLD.Village.village import Village


def test_village_creates_world():
    village = Village()

    world = village.create()

    assert world is not None


def test_village_has_buildings():
    world = Village().create()

    assert len(world.buildings) == 4


def test_village_has_npcs():
    world = Village().create()

    assert len(world.npcs) == 4


def test_village_contains_farmer():
    world = Village().create()

    farmers = [
        npc
        for npc in world.npcs
        if npc.role == "farmer"
    ]

    assert len(farmers) == 2


def test_village_contains_shopkeeper():
    world = Village().create()

    shopkeepers = [
        npc
        for npc in world.npcs
        if npc.role == "shopkeeper"
    ]

    assert len(shopkeepers) == 1