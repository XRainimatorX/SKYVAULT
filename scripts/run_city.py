"""Run the city reference scenarios and the supply delay study (Phase 14).

    python3 scripts/run_city.py

Writes output/city/: each scenario's governance stability score
(governance_<scenario>.json), the blackout's cascade (cascade_<scenario>.json),
the supply delay study (supply_delay.json) and city_report.md for a person
to read.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.domains.city.pack import CITY  # noqa: E402
from skyvault.domains.city.report import cascade, city_report  # noqa: E402
from skyvault.engine import SkyVaultTacticalReferenceEngine  # noqa: E402
from skyvault.scenario_loader import load_scenario  # noqa: E402

SCENARIOS = ("city_takeover_001", "city_blackout_001")
FACTORS = (1.0, 1.5, 2.0, 2.5, 3.0)


def run(scenario: dict) -> dict:
    package: dict = SkyVaultTacticalReferenceEngine(copy.deepcopy(scenario)).run()
    return package


def write(folder: Path, name: str, data: object) -> None:
    (folder / name).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def delay_study(scenario: dict, seeds: list[int]) -> dict:
    """End order and score of the takeover at each delay factor, over seeds."""
    rows = []
    for factor in FACTORS:
        outcomes, orders, scores = [], [], []
        for seed in seeds:
            variant = copy.deepcopy(scenario)
            variant["runtime"]["random_seed"] = seed
            variant["world_contract"]["rule_set"]["city"]["supply"][
                "delay_factor"
            ] = factor
            package = run(variant)
            governance = CITY.governance_outcome(package, variant)
            outcomes.append(package["evaluation_result"]["winner_or_result"])
            orders.append(governance["components"]["order"] * 100)
            scores.append(governance["score"])
        rows.append(
            {
                "delay_factor": factor,
                "restored_rate": round(
                    sum(o in ("order_restored", "order_held") for o in outcomes)
                    / len(outcomes),
                    4,
                ),
                "mean_end_order": round(sum(orders) / len(orders), 2),
                "mean_score": round(sum(scores) / len(scores), 4),
                "outcomes": {o: outcomes.count(o) for o in sorted(set(outcomes))},
            }
        )
    return {"scenario": scenario["scenario_id"], "seeds": seeds, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", default=str(REPO_ROOT / "output" / "city"))
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)

    summary: dict = {"scenarios": {}}
    for name in SCENARIOS:
        scenario = load_scenario(REPO_ROOT / "data" / "scenarios" / name / "v0.1.json")
        package = run(scenario)
        governance = CITY.governance_outcome(package, scenario)
        chain = cascade(package)
        verdict = package["evaluation_result"]
        write(folder, f"governance_{name}.json", governance)
        write(folder, f"cascade_{name}.json", chain)
        summary["scenarios"][name] = {
            "outcome": verdict["winner_or_result"],
            "verdict": verdict["overall_judgement"]["status"],
            "governance": governance,
            "cascade": chain,
        }
        print(
            f"{name}: {verdict['winner_or_result']}, governance score "
            f"{governance['score']:.2f}, cascade depth {chain['cascade_depth']}"
        )
    takeover = load_scenario(REPO_ROOT / "data/scenarios/city_takeover_001/v0.1.json")
    seed = int(takeover["runtime"]["random_seed"])
    summary["supply_delay"] = delay_study(
        takeover, [seed + n for n in range(args.seeds)]
    )
    write(folder, "supply_delay.json", summary["supply_delay"])
    for row in summary["supply_delay"]["rows"]:
        print(
            f"supply delay x{row['delay_factor']:g}: restored "
            f"{row['restored_rate']:.0%}, mean end order {row['mean_end_order']:.1f}"
        )
    (folder / "city_report.md").write_text(city_report(summary), encoding="utf-8")
    print(f"wrote {folder}")


if __name__ == "__main__":
    main()
