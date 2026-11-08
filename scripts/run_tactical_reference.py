import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.causal_chain import build_causal_chain
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.entity_history import build_entity_history
from skyvault.evaluation import render_tradeoff_report
from skyvault.replay import build_replay_state_at_tick
from skyvault.reproducibility import RunRegistry
from skyvault.scenario_loader import load_evaluation_profile, load_scenario
from skyvault.timeline import render_timeline


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        file.write(text)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the tactical reference slice.")
    parser.add_argument(
        "--scenario",
        type=Path,
        default=SCENARIO_DIR / "tactical_reference_001" / "v0.1.json",
        help="scenario file; default: tactical_reference_001 v0.1",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REPO_ROOT / "runs" / "registry.jsonl",
        help="run registry to append to; default: runs/registry.jsonl",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="evaluation profile (JSON or YAML); default: balanced",
    )
    args = parser.parse_args(argv)

    output_dir = REPO_ROOT / "output"

    scenario = load_scenario(args.scenario)
    profile = load_evaluation_profile(args.profile) if args.profile else None

    engine = SkyVaultTacticalReferenceEngine(scenario, evaluation_profile=profile)
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

    write_json(
        output_dir / "evaluation_result.json",
        result_package["evaluation_result"],
    )

    write_json(
        output_dir / "score_breakdown.json",
        result_package["score_breakdown"],
    )

    write_json(
        output_dir / "anti_gaming_report.json",
        result_package["anti_gaming_report"],
    )

    write_text(
        output_dir / "tradeoff_report.md",
        render_tradeoff_report(result_package["tradeoff_report"]),
    )

    entry = RunRegistry(args.registry).record(result_package)

    evaluation = result_package["evaluation_result"]
    judgement = evaluation["overall_judgement"]

    print("SKYVAULT Tactical Reference Slice v0.1 completed.")
    version = result_package["scenario_version"]
    print(f"Scenario: {result_package['scenario_id']} {version}")
    print(f"Result: {evaluation['winner_or_result']}")
    print(f"Events: {evaluation['event_count']}")
    print(
        f"Verdict: {judgement['status']} "
        f"(score {evaluation['overall_score']:.2f}, profile {evaluation['profile_id']})"
    )
    print(f"Run: {entry['run_id']} (output {entry['output_hash'][:12]})")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
