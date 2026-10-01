import pytest

from WORLD.Genesis.scenario import WorldScenario


def test_scenario_has_declarative_defaults():
    scenario = WorldScenario()

    assert scenario.era
    assert scenario.geography
    assert scenario.climate
    assert scenario.population >= 0
    assert isinstance(scenario.resources, dict)
    assert isinstance(scenario.buildings, list)


def test_scenario_accepts_world_definition():
    scenario = WorldScenario(
        era="15th century",
        geography="small coastal settlement",
        climate="dry",
        population=40,
        resources={
            "Food": 100,
            "Wood": 200,
        },
        buildings=[
            "Village Farm",
            "General Store",
        ],
        factions=["Regional Ruler"],
        landmarks=["Forest", "River"],
    )

    assert scenario.era == "15th century"
    assert scenario.geography == "small coastal settlement"
    assert scenario.climate == "dry"
    assert scenario.population == 40
    assert scenario.resources["Food"] == 100
    assert scenario.buildings == ["Village Farm", "General Store"]
    assert scenario.factions == ["Regional Ruler"]
    assert scenario.landmarks == ["Forest", "River"]


def test_scenario_rejects_empty_era():
    with pytest.raises(ValueError):
        WorldScenario(era="   ")


def test_scenario_rejects_negative_population():
    with pytest.raises(ValueError):
        WorldScenario(population=-1)


def test_scenario_rejects_negative_resource_quantity():
    with pytest.raises(ValueError):
        WorldScenario(resources={"Food": -1})


def test_scenario_rejects_empty_resource_name():
    with pytest.raises(ValueError):
        WorldScenario(resources={" ": 10})


def test_scenario_rejects_empty_building_name():
    with pytest.raises(ValueError):
        WorldScenario(buildings=["   "])
