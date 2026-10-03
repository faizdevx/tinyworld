import json

import pytest

from WORLD.AI.beliefs import Belief
from WORLD.Genesis.scenario import WorldScenario
from WORLD.Interventions import GodIntervention, InterventionOperation
from WORLD.NPCs.npc import NPC
from WORLD.Observatory import (
    Checkpoint,
    Experiment,
    ExperimentRunner,
    Observatory,
    WorldSnapshot,
)
from WORLD.world import World


def make_world():
    world = World(seed=42)
    world.metadata["army_strength"] = 500
    world.metadata["weather"] = "clear"
    world.resources["Food"] = world.resources["Food"]

    rahul = NPC(name="Rahul", role="guard", money=20, home="House 1", location="Village Square")
    sara = NPC(name="Sara", role="merchant", money=30, home="House 2", location="Village Square")
    ali = NPC(name="Ali", role="farmer", money=15, home="House 3", location="Market")
    rahul.beliefs = [
        Belief(subject="foreign_army", predicate="strength", value=100, confidence=0.8, source="npc:Rahul", origin_type="communication")
    ]
    sara.beliefs = [
        Belief(subject="foreign_army", predicate="strength", value=800, confidence=0.7, source="npc:Ali", origin_type="communication")
    ]
    world.add_npc(rahul)
    world.add_npc(sara)
    world.add_npc(ali)
    return world, rahul, sara, ali


def test_experiment_creation_and_seed_recording():
    scenario = WorldScenario(
        era="Bronze Age",
        geography="valley",
        climate="temperate",
        population=3,
        resources={"Food": 30},
        buildings=["House"],
        factions=["Village Council"],
        landmarks=["Forest"],
    )
    experiment = Experiment(
        experiment_id="EXP-001",
        seed=42,
        scenario=scenario,
        interventions=[
            GodIntervention(
                operation=InterventionOperation.SPAWN,
                target="entity:Foreign Army",
                properties={"location": "Forest", "size": 500},
            )
        ],
    )

    assert experiment.experiment_id == "EXP-001"
    assert experiment.seed == 42
    assert experiment.scenario.era == "Bronze Age"
    assert experiment.interventions[0].target == "entity:Foreign Army"


def test_world_snapshot_is_read_only_and_structural():
    world, _, _, _ = make_world()
    observatory = Observatory()
    snapshot = observatory.inspect_world(world)

    assert isinstance(snapshot, WorldSnapshot)
    assert snapshot.metadata["army_strength"] == 500
    assert snapshot.population == 3

    with pytest.raises((AttributeError, TypeError)):
        snapshot.metadata["army_strength"] = 100

    world.metadata["army_strength"] = 999
    assert snapshot.metadata["army_strength"] == 500


def test_npc_snapshot_is_private_and_not_live_object():
    world, rahul, _, _ = make_world()
    snapshot = Observatory().inspect_npc(world, "npc:Rahul")

    assert snapshot.name == "Rahul"
    assert snapshot.location == "Village Square"
    assert snapshot.beliefs[0].subject == "foreign_army"
    with pytest.raises((AttributeError, TypeError)):
        snapshot.beliefs[0].value = 999
    rahul.location = "Forest"
    assert snapshot.location == "Village Square"


def test_reality_comparison_distinguishes_truth_from_unknown():
    world, rahul, sara, ali = make_world()
    observatory = Observatory()

    comparison = observatory.compare_beliefs(world)
    assert any(item.subject == "foreign_army" and item.npc_value == 100 and item.world_value == 500 for item in comparison)
    assert any(item.subject == "foreign_army" and item.npc_name == "Ali" and item.known is False for item in comparison)
    assert any(item.subject == "foreign_army" and item.npc_name == "Sara" and item.npc_value == 800 for item in comparison)


def test_checkpoint_save_and_load_round_trip():
    world, _, _, _ = make_world()
    observatory = Observatory()
    checkpoint = observatory.save_checkpoint(world, "CK-001", path="./tmp_checkpoint.json")
    loaded = observatory.load_checkpoint("./tmp_checkpoint.json")

    assert checkpoint.checkpoint_id == "CK-001"
    assert loaded.seed == 42
    assert loaded.world_state["metadata"]["army_strength"] == 500
    assert loaded.npc_state[0]["name"] == "Rahul"


def test_experiment_runner_reproduces_structurally_equivalent_runs():
    scenario = WorldScenario(
        era="Bronze Age",
        geography="valley",
        climate="temperate",
        population=2,
        resources={"Food": 20},
        buildings=["House"],
        factions=["Village Council"],
        landmarks=["Forest"],
    )
    runner = ExperimentRunner(seed=7)
    first = runner.run_experiment(experiment_id="EXP-001", scenario=scenario, interventions=[])
    second = runner.run_experiment(experiment_id="EXP-001", scenario=scenario, interventions=[])

    assert first.experiment_id == second.experiment_id
    assert first.seed == second.seed
    assert first.metrics == second.metrics
    assert first.snapshots == second.snapshots
