import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def main() -> None:
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"
    output_dir = REPO_ROOT / "output"

    scenario = load_scenario(scenario_path)

    engine = SkyVaultTacticalReferenceEngine(scenario)
    result_package = engine.run()

    write_json(
        output_dir / "result_package.json",
        result_package,
    )

    write_json(
        output_dir / "event_memory.json",
        result_package["event_memory"],
    )

    write_json(
        output_dir / "final_state.json",
        result_package["final_world_state"],
    )

    write_json(
        output_dir / "causal_chain.json",
        result_package,
    )

    write_json(
        output_dir / "replay_state_at_tick.json",
        result_package,
    )

    print("SKYVAULT Tactical Reference Slice v0.1 completed.")
    print(f"Scenario: {result_package['scenario_id']}")
    print(f"Result: {result_package['evaluation']['winner_or_result']}")
    print(f"Events: {result_package['evaluation']['event_count']}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()