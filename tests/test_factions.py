import pytest

from WORLD.Factions.faction import Faction


def test_faction_stores_name_and_type():
    faction = Faction(name="Regional Ruler", faction_type="ruler")

    assert faction.name == "Regional Ruler"
    assert faction.faction_type == "ruler"


def test_faction_rejects_empty_name():
    with pytest.raises(ValueError):
        Faction(name="   ", faction_type="ruler")


def test_faction_rejects_empty_type():
    with pytest.raises(ValueError):
        Faction(name="Regional Ruler", faction_type="   ")