import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.contracts import build_json_schemas

SCHEMA_DIR = SRC_PATH / "skyvault" / "schemas"


def main() -> None:
    """
    Write every contract's JSON Schema to src/skyvault/schemas/.

    Run this after changing a contract. tests/contracts/test_result_contracts.py
    fails while the committed files differ from what the contracts generate.
    """
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    schemas = build_json_schemas()

    for name, schema in schemas.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False)
        path.write_text(text + "\n", encoding="utf-8")

    print(f"Wrote {len(schemas)} schemas to {SCHEMA_DIR}")


if __name__ == "__main__":
    main()
