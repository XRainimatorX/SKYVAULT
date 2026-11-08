"""Build the city reference scenarios from their specs.

    python3 scripts/build_city_scenarios.py

Writes data/scenarios/city_*/<version>.json from the rules and specs in
data/domains/city/. Run it after changing the rules or a spec; a test fails
while the committed scenarios differ from what this builds.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.domains.city.reference import (  # noqa: E402
    reference_scenarios,
    scenario_path,
)


def main() -> None:
    for name, scenario in reference_scenarios().items():
        path = scenario_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(scenario, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        districts = sum(
            1 for e in scenario["entities"] if e["entity_type"] == "district"
        )
        print(f"{name}: {districts} districts, {len(scenario['entities'])} entities")


if __name__ == "__main__":
    main()
