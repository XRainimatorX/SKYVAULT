"""Run SKYVAULT as a background world service.

    python3 scripts/serve_world.py      # SQLite store, jobs on this process's threads
    python3 scripts/serve_world.py --queue rq --redis redis://localhost:6379/0 \
        --store postgresql://skyvault:skyvault@localhost/skyvault

With --queue rq the API only queues; run scripts/world_worker.py (same
--store, --redis and --governance) to execute jobs. The API's own docs are
at /api/docs. Outside systems use the external interface on the same app
(Phase 12): /scenario/submit, /world/create, /action/submit, /run/{run_id},
/branch_compare/run, /failure_exploration/run, /conflict/{id} and
/branch_conflict/resolve.

    python3 scripts/serve_world.py --edition commercial

serves one edition (Phase 19, data/editions/): the commercial shell mounts
no internal system adapter, runs only its job kinds and domains, offers its
products at /api/products and redacts every internal name from what it
returns. Without --edition the service is the internal core as before.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.editions.manifest import load_edition
from skyvault.editions.service import create_edition_service, edition_policy
from skyvault.worldservice.api import create_world_service, in_process_queue
from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.queues import RQQueue
from skyvault.worldservice.store import open_store


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the SKYVAULT world service.")
    parser.add_argument(
        "--store", default=f"sqlite:///{REPO_ROOT / 'runs' / 'service.sqlite'}"
    )
    parser.add_argument("--queue", choices=["inprocess", "rq"], default="inprocess")
    parser.add_argument("--redis", default="redis://localhost:6379/0")
    parser.add_argument(
        "--governance", default="governance", help="data/service/<name>.json or a path"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--edition", default=None, help="data/editions/<name>.json")
    args = parser.parse_args(argv)

    import uvicorn

    if args.store.startswith("sqlite:///"):
        Path(args.store[len("sqlite:///") :]).parent.mkdir(parents=True, exist_ok=True)
    store = open_store(args.store)
    policy = load_governance(args.governance)
    if args.edition is not None:
        edition = load_edition(args.edition)
        rq = (
            RQQueue(
                args.redis, store.spec, args.governance, edition_policy(edition, policy)
            )
            if args.queue == "rq"
            else None
        )
        app = create_edition_service(edition, store, rq, policy)
    else:
        queue = (
            RQQueue(args.redis, store.spec, args.governance, policy)
            if args.queue == "rq"
            else in_process_queue(store, policy)
        )
        app = create_world_service(store, queue, policy)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
