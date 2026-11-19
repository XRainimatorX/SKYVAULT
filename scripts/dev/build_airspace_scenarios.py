"""Build the airspace reference scenarios from their specs.

    python3 scripts/dev/build_airspace_scenarios.py

Writes the world contracts (data/worlds/airspace_*) and the scenarios
(data/scenarios/airspace_*/<version>.json) from the rules and specs in
data/domains/airspace/. Run it after changing the rules or a spec; a test fails
while the committed scenarios differ from what this builds.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.domains.airspace.reference import reference_files

DATA = REPO_ROOT / "data"


def main() -> None:
    for name, document in reference_files().items():
        path = DATA / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(name)


if __name__ == "__main__":
    main()
