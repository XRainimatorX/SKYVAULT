import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.replay import build_replay_state_at_tick
from skyvault.scenario_loader import load_scenario


def build_reference_replay() -> dict:
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    return build_replay_state_at_tick(
        result_package["initial_world_state"],
        result_package["event_memory"],
        result_package["final_world_state"],
    )


def test_replay_has_required_keys():
    replay = build_reference_replay()

    assert "scenario_id" in replay
    assert replay["scenario_id"] == "tactical_reference_001"
    assert "states" in replay
    assert "0" in replay["states"]
    assert "final" in replay["states"]


def test_replay_has_at_least_one_numeric_tick():
    replay = build_reference_replay()

    numeric_ticks = [
        int(tick) for tick in replay["states"] if tick.isdigit() and int(tick) > 0
    ]

    assert len(numeric_ticks) > 0


def test_replay_each_tick_has_description_and_world_state():
    replay = build_reference_replay()

    for _tick, state in replay["states"].items():
        assert "description" in state
        assert "world_state" in state
        assert len(state["world_state"]) > 0

    assert len(replay["states"]["final"]["world_state"]) > 0


def test_replay_output_is_json_serializable():
    replay = build_reference_replay()

    encoded = json.dumps(replay)

    assert json.loads(encoded) == replay
