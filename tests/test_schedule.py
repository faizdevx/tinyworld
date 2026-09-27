from WORLD.NPCs.npc import NPC
from WORLD.Schedules.schedule import ScheduleSystem


def create_rahul():
    return NPC(
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
            12: "General Store",
            13: "General Store",
            14: "General Store",
            15: "Village Farm",
            16: "Village Farm",
            17: "Village Farm",
            18: "House 1",
            19: "House 1",
            20: "House 1",
            21: "House 1",
        },
    )


def test_farmer_goes_to_farm_at_8():
    rahul = create_rahul()
    system = ScheduleSystem()

    system.update_npc(rahul, 8)

    assert rahul.location == "Village Farm"


def test_farmer_stays_at_farm_at_10():
    rahul = create_rahul()
    system = ScheduleSystem()

    system.update_npc(rahul, 10)

    assert rahul.location == "Village Farm"


def test_farmer_goes_to_shop_at_12():
    rahul = create_rahul()
    system = ScheduleSystem()

    system.update_npc(rahul, 12)

    assert rahul.location == "General Store"


def test_farmer_goes_home_at_18():
    rahul = create_rahul()
    system = ScheduleSystem()

    system.update_npc(rahul, 18)

    assert rahul.location == "House 1"


def test_missing_schedule_hour_defaults_to_home():
    rahul = create_rahul()
    system = ScheduleSystem()

    system.update_npc(rahul, 2)

    assert rahul.location == "House 1"