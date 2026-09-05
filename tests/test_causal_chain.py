import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.causal_chain import build_causal_chain
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario


def run_reference_scenario() -> dict:
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    return engine.run()


def test_causal_chain_has_required_keys():
    result_package = run_reference_scenario()

    causal_chain = build_causal_chain(
        result_package["scenario_id"],
        result_package["event_memory"],
    )

    assert causal_chain["scenario_id"] == "tactical_reference_001"
    assert "chains" in causal_chain
    assert isinstance(causal_chain["chains"], list)
    assert len(causal_chain["chains"]) > 0


def test_every_source_action_id_is_grouped():
    result_package = run_reference_scenario()

    causal_chain = build_causal_chain(
        result_package["scenario_id"],
        result_package["event_memory"],
    )

    expected = {
        event["source_action_id"]
        for event in result_package["event_memory"]
        if event["source_action_id"] is not None
        and event["event_type"] != "SCENARIO_END"
    }

    grouped = {chain["source_action_id"] for chain in causal_chain["chains"]}

    assert expected == grouped
    assert None not in grouped


def test_each_chain_has_required_fields():
    result_package = run_reference_scenario()

    causal_chain = build_causal_chain(
        result_package["scenario_id"],
        result_package["event_memory"],
    )

    for chain in causal_chain["chains"]:
        assert "source_action_id" in chain
        assert "events" in chain
        assert "event_types" in chain
        assert "summary" in chain
        assert isinstance(chain["events"], list)
        assert isinstance(chain["event_types"], list)
        assert len(chain["events"]) > 0
        assert chain["summary"] != ""


def test_events_in_each_chain_are_sorted_by_time():
    result_package = run_reference_scenario()

    events_by_id = {
        event["event_id"]: event for event in result_package["event_memory"]
    }

    causal_chain = build_causal_chain(
        result_package["scenario_id"],
        result_package["event_memory"],
    )

    for chain in causal_chain["chains"]:
        times = [events_by_id[event_id]["time"] for event_id in chain["events"]]

        assert times == sorted(times)
