"""Serve the SKYVAULT UI and its API for a workspace.

    python3 scripts/serve_ui.py
    python3 scripts/serve_ui.py --workspace output --port 8000

Build the UI first (cd ui && npm ci && npm run build); without ui/out only
the API (/api/..., /ws/replay) is served. The workspace (default: output/)
needs result_package.json.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


import uvicorn

from skyvault.service import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the SKYVAULT UI.")
    parser.add_argument("--workspace", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--ui", type=Path, default=REPO_ROOT / "ui" / "out")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if not (args.ui / "index.html").is_file():
        print(f"No UI build in {args.ui}; serving the API only")
    print(f"SKYVAULT UI: http://{args.host}:{args.port}")
    uvicorn.run(create_app(args.workspace, args.ui), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
