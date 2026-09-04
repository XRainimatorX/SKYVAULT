import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.causal_chain import build_causal_chain
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.entity_history import build_entity_history
from skyvault.replay import build_replay_state_at_tick
from skyvault.scenario_loader import load_scenario
from skyvault.timeline import render_timeline


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        file.write(text)


def main() -> None:
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"
    output_dir = REPO_ROOT / "output"

    scenario = load_scenario(scenario_path)

    engine = SkyVaultTacticalReferenceEngine(scenario)
    result_package = engine.run()

    event_memory = result_package["event_memory"]
    initial_world_state = result_package["initial_world_state"]
    final_world_state = result_package["final_world_state"]
    scenario_id = result_package["scenario_id"]

    write_json(
        output_dir / "result_package.json",
        result_package,
    )

    write_json(
        output_dir / "event_memory.json",
        event_memory,
    )

    write_json(
        output_dir / "final_state.json",
        final_world_state,
    )

    write_json(
        output_dir / "replay_state_at_tick.json",
        build_replay_state_at_tick(
            initial_world_state,
            event_memory,
            final_world_state,
        ),
    )

    write_json(
        output_dir / "causal_chain.json",
        build_causal_chain(scenario_id, event_memory),
    )

    write_json(
        output_dir / "entity_history.json",
        build_entity_history(initial_world_state, event_memory),
    )

    write_text(
        output_dir / "timeline.txt",
        render_timeline(scenario_id, event_memory),
    )

    print("SKYVAULT Tactical Reference Slice v0.1 completed.")
    print(f"Scenario: {result_package['scenario_id']}")
    print(f"Result: {result_package['evaluation']['winner_or_result']}")
    print(f"Events: {result_package['evaluation']['event_count']}")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
