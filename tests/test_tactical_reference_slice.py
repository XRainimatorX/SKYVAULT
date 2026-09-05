import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario


def test_scenario_loads():
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)

    assert scenario["scenario_id"] == "tactical_reference_001"
    assert "world_contract" in scenario
    assert "entities" in scenario


def test_engine_runs_and_creates_events():
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    assert result_package["scenario_id"] == "tactical_reference_001"
    assert len(result_package["event_memory"]) > 0
    assert result_package["evaluation"]["event_count"] > 0


def test_event_has_before_and_after_state():
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    events = result_package["event_memory"]

    state_change_events = [
        event
        for event in events
        if event["event_type"] in ["MOVE", "ATTACK", "ENTITY_DESTROYED"]
    ]

    assert len(state_change_events) > 0

    first_event = state_change_events[0]

    assert "before_state" in first_event
    assert "after_state" in first_event


def test_result_package_carries_initial_and_final_world_state():
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    initial_world_state = result_package["initial_world_state"]

    assert initial_world_state["tick"] == 0
    assert len(initial_world_state["entities"]) == len(scenario["entities"])

    for entity in scenario["entities"]:
        recorded = initial_world_state["entities"][entity["entity_id"]]

        assert recorded["state"] == entity["state"]
        assert recorded["position"] == entity["position"]

    assert result_package["final_world_state"] != initial_world_state


def test_evaluation_event_count_matches_event_memory():
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    event_count = result_package["evaluation"]["event_count"]

    key_findings = result_package["evaluation"]["key_findings"]

    assert event_count == len(result_package["event_memory"])
    assert f"Events recorded: {event_count}" in key_findings


def test_policy_is_separated_from_world_state():
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    assert hasattr(engine, "policy")
    assert engine.policy.__class__.__name__ == "TacticalReferencePolicy"
