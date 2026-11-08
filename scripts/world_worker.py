"""Run an RQ worker for the world service (with serve_world.py --queue rq).

    python3 scripts/world_worker.py --redis redis://localhost:6379/0 \
        --store postgresql://skyvault:skyvault@localhost/skyvault

The worker takes jobs from the highest priority queue first and executes
them under the governance policy. --burst stops once the queues are empty.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.worldservice.queues import RQQueue


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run a SKYVAULT world worker.")
    parser.add_argument(
        "--store", default=f"sqlite:///{REPO_ROOT / 'runs' / 'service.sqlite'}"
    )
    parser.add_argument("--redis", default="redis://localhost:6379/0")
    parser.add_argument("--governance", default="governance")
    parser.add_argument("--burst", action="store_true")
    args = parser.parse_args(argv)

    queue = RQQueue(args.redis, args.store, args.governance)
    queue.worker(burst=args.burst).work(burst=args.burst)


if __name__ == "__main__":
    main()
