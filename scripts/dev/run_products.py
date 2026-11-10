"""Run every product of an edition and write what each shows a customer.

    python3 scripts/dev/run_products.py --edition commercial

Writes output/products/: one <product>.json per product (its question, key
figures and conclusion, redacted for the edition) and products.md for a
person to read. --repeats sets the runs of the products that repeat.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.editions.manifest import load_edition  # noqa: E402
from skyvault.editions.products import product_report, run_product  # noqa: E402
from skyvault.editions.redact import leaks  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--edition", default="commercial")
    parser.add_argument("--output", default=str(REPO_ROOT / "output" / "products"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    edition = load_edition(args.edition)
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for product_id in edition["products"]:
        result = run_product(product_id, edition, repeats=args.repeats)
        found = leaks(result, edition)
        if found:
            raise SystemExit(f"{product_id} leaks internal names: {found}")
        results.append(result)
        (folder / f"{product_id}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"{result['title']:<36} {result['conclusion']}")
    (folder / "products.md").write_text(product_report(results, edition), "utf-8")
    print(f"wrote {folder}")


if __name__ == "__main__":
    main()
