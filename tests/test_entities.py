import pytest

from WORLD.Entities.entity import WorldEntity


def test_world_entity_stores_name_and_type():
    entity = WorldEntity(name="Forest", entity_type="forest")

    assert entity.name == "Forest"
    assert entity.entity_type == "forest"


def test_world_entity_rejects_empty_name():
    with pytest.raises(ValueError):
        WorldEntity(name="   ", entity_type="forest")


def test_world_entity_rejects_empty_type():
    with pytest.raises(ValueError):
        WorldEntity(name="Forest", entity_type="   ")