"""Run Full SKYVAULT v2.0's acceptance on one service and write what it found.

    python3 scripts/run_v2_acceptance.py

Writes output/v2/: acceptance.json (every check with its evidence) and
acceptance.md for a person to read. Exits 1 when any check fails.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.acceptance.report import acceptance_report  # noqa: E402
from skyvault.acceptance.run import run_acceptance  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", default=str(REPO_ROOT / "output" / "v2"))
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    result = run_acceptance()
    (folder / "acceptance.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (folder / "acceptance.md").write_text(acceptance_report(result), encoding="utf-8")
    for name, count in result["counts"].items():
        print(f"{name:<11} {count['passed']}/{count['of']}")
    print(f"{'ACCEPTED' if result['passed'] else 'NOT ACCEPTED'} — wrote {folder}")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
