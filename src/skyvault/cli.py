"""skyvault = the one command SKYVAULT is started and used with (Phase 21).

    skyvault serve                          # the world service, its worker and the UI
    skyvault run military_urban_001/v0.2    # submit a run, wait, print what it came to
    skyvault explore military_urban_001/v0.2
    skyvault batch military_doctrine
    skyvault runs                           # what the UI can show
    skyvault briefing latest --format pdf
    skyvault acceptance                     # the v2.0 acceptance, in this process

Important:
serve and worker start the service; every command after them talks to a
running service over HTTP (--url, or SKYVAULT_URL; default
http://127.0.0.1:8000), the way an outside system does. virtual-test and
acceptance compute in this process: they need no service. Nothing here
reads a development script or the tests' fixtures; a deployment adds its
own scenarios, batches and policies through SKYVAULT_SCENARIO_PATH,
SKYVAULT_BATCH_PATH and SKYVAULT_POLICY_MODULES.
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_BUILD = REPO_ROOT / "ui" / "out"
DEFAULT_URL = "http://127.0.0.1:8000"
FINISHED = ("completed", "failed", "replayed", "deleted")
REPORT_TYPES = {"md": "report.md", "pdf": "report.pdf", "docx": "report.docx"}


class Failed(Exception):
    """A command that could not do what was asked; its message is for a person."""


# ── the service ──────────────────────────────────────────────────────────────


def build_app(args: argparse.Namespace) -> Any:
    """The world service an edition shows, with the UI mounted last."""
    from .editions.manifest import load_edition
    from .editions.service import create_edition_service, edition_policy
    from .service import mount_ui
    from .worldservice.governance import load_governance
    from .worldservice.queues import RQQueue
    from .worldservice.store import open_store

    if args.store.startswith("sqlite:///"):  # relative, or absolute with four
        Path(args.store[len("sqlite:///") :]).parent.mkdir(parents=True, exist_ok=True)
    store = open_store(args.store)
    policy = load_governance(args.governance)
    edition = load_edition(args.edition)
    queue = (
        RQQueue(
            args.redis, store.spec, args.governance, edition_policy(edition, policy)
        )
        if args.queue == "rq"
        else None
    )
    app = create_edition_service(edition, store, queue, policy)
    mount_ui(app, Path(args.ui) if args.ui else None)
    return app


def serve(args: argparse.Namespace) -> None:
    import uvicorn

    app = build_app(args)
    print(
        f"SKYVAULT {__version__} ({args.edition} edition) on http://{args.host}:{args.port}"
    )
    uvicorn.run(app, host=args.host, port=args.port)


def worker(args: argparse.Namespace) -> None:
    from .worldservice.queues import RQQueue

    queue = RQQueue(args.redis, args.store, args.governance)
    queue.worker(burst=args.burst).work(burst=args.burst)


# ── talking to a running service ─────────────────────────────────────────────


class Client:
    """The service at url, over HTTP; a refusal raises Failed with its reason."""

    def __init__(self, url: str, http: Any = None) -> None:
        import httpx

        self.http = http or httpx.Client(base_url=url, timeout=60.0)
        self.url = url

    def call(self, method: str, path: str, body: Any = None) -> Any:
        import httpx

        try:
            response = self.http.request(method, path, json=body)
        except httpx.TransportError as error:
            raise Failed(
                f"no SKYVAULT service at {self.url} ({error}); "
                "start one with: skyvault serve"
            ) from None
        if response.status_code >= 400:
            detail = (
                response.json().get("detail") if _is_json(response) else response.text
            )
            if isinstance(detail, dict):
                detail = f"{detail.get('reason')}: {detail.get('detail')}"
            raise Failed(f"{method} {path} → {response.status_code} {detail}")
        return response.json() if _is_json(response) else response.content

    def wait(self, job_id: str, every: float = 0.2) -> dict[str, Any]:
        while True:
            job: dict[str, Any] = self.call("GET", f"/api/jobs/{job_id}")
            if job["lifecycle_state"] in FINISHED:
                return job
            time.sleep(every)


def _is_json(response: Any) -> bool:
    return "application/json" in response.headers.get("content-type", "")


def submit(client: Client, request: dict[str, Any], wait: bool) -> dict[str, Any]:
    job: dict[str, Any] = client.call(
        "POST", "/api/jobs", {"source_system": "user", **request}
    )
    print(f"{job['job_id']}  {request['kind']}  queued")
    if not wait:
        return job
    done = client.wait(job["job_id"])
    print(f"{done['job_id']}  {done['lifecycle_state']}")
    for key, value in sorted(done["summary"].items()):
        if key not in ("handoff", "external_submission") and value is not None:
            print(f"  {key}: {value}")
    if done["summary"].get("handoff"):
        print(f"  handoff: {done['summary']['handoff']['required_decision']}")
    if done["lifecycle_state"] == "failed":
        raise Failed(f"{done['job_id']} failed: {done['error']}")
    return done


def run(args: argparse.Namespace, client: Client) -> None:
    request: dict[str, Any] = {"kind": "scenario_run", "scenario": args.scenario}
    if args.seed is not None:
        request["runtime"] = {"random_seed": args.seed}
    if args.profile:
        request["profile"] = args.profile
    submit(client, request, not args.no_wait)


def explore(args: argparse.Namespace, client: Client) -> None:
    request: dict[str, Any] = {"kind": "failure_exploration", "scenario": args.scenario}
    if args.repeat is not None:
        request["repeat_count"] = args.repeat
    submit(client, request, not args.no_wait)


def batch(args: argparse.Namespace, client: Client) -> None:
    request: dict[str, Any] = {"kind": "batch", "batch": args.name}
    if args.repeat is not None:
        request["repeat_count"] = args.repeat
    submit(client, request, not args.no_wait)


def replay(args: argparse.Namespace, client: Client) -> None:
    job = client.call("POST", f"/api/jobs/{args.job}/replay")
    print(f"{job['job_id']}  replay of {args.job}  queued")
    if not args.no_wait:
        done = client.wait(job["job_id"])
        print(f"{done['job_id']}  reproduced: {done['summary'].get('reproduced')}")


def cancel(args: argparse.Namespace, client: Client) -> None:
    job = client.call("POST", f"/api/jobs/{args.job}/cancel")
    print(f"{job['job_id']}  {job['lifecycle_state']}")


def world(args: argparse.Namespace, client: Client) -> None:
    if args.action == "create":
        state = client.call("POST", "/api/worlds", {"scenario": args.target})
    elif args.action == "advance":
        state = client.call(
            "POST", f"/api/worlds/{args.target}/advance", {"ticks": args.ticks}
        )
    else:
        client.call("POST", f"/api/worlds/{args.target}/finish")
        state = client.call("GET", f"/api/jobs/{args.target}")
        state = {"world_id": args.target, "lifecycle_state": state["lifecycle_state"]}
    print(json.dumps(state, indent=2, sort_keys=True))


def status(args: argparse.Namespace, client: Client) -> None:
    found = client.call("GET", "/api/status")
    service = found["service_status"]
    print(f"{service['mode']} ({service['health']})  queue {found['queue']['depth']}")
    for state, count in found["jobs"].items():
        print(f"  {state}: {count}")


def runs(args: argparse.Namespace, client: Client) -> None:
    listed = client.call("GET", "/api/runs")
    if not listed:
        print("No run yet: skyvault run <scenario>/<version>")
    for entry in listed:
        print(
            f"{entry['run']}  {entry['scenario_id']} {entry['scenario_version']}  "
            f"{entry['result']}  {entry['events']} events  {entry['output_hash']}"
        )


def result(args: argparse.Namespace, client: Client) -> None:
    found = client.call("GET", f"/api/jobs/{args.job}/result")
    text = json.dumps(found, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)


def briefing(args: argparse.Namespace, client: Client) -> None:
    content = client.call("GET", f"/api/runs/{args.run}/{REPORT_TYPES[args.format]}")
    if args.out is None and args.format == "md":
        sys.stdout.write(content.decode("utf-8"))
        return
    out = Path(args.out or f"briefing.{args.format}")
    out.write_bytes(content)
    print(f"wrote {out}")


def products(args: argparse.Namespace, client: Client) -> None:
    if args.product is None:
        for entry in client.call("GET", "/api/products"):
            print(f"{entry['product']:<22} {entry['question']}")
        return
    found = client.call("POST", f"/api/products/{args.product}")
    print(f"{found['title']}: {found['question']}")
    for name, value in found.get("kpis", {}).items():
        print(f"  {name}: {value}")
    if found.get("conclusion"):
        print(found["conclusion"])


# ── computed here ────────────────────────────────────────────────────────────


def virtual_test_command(args: argparse.Namespace) -> None:
    from .contracts import validate_equipment_profile
    from .virtualtest.profile import load_profile
    from .virtualtest.run import virtual_test

    path = Path(args.profile)
    profile = (
        validate_equipment_profile(json.loads(path.read_text(encoding="utf-8")))
        if path.suffix == ".json"
        else load_profile(args.profile)
    )
    found = virtual_test(profile)
    judgement = found["final_judgement"]
    print(
        f"{profile['equipment_id']}"
        f"  physical {found['physical_possibility']['score']:.3f}"
        f"  engineering {found['engineering_feasibility']['score']:.3f}"
        f"  → {judgement['status']}"
    )
    if args.out:
        Path(args.out).write_text(json.dumps(found, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.out}")


def acceptance(args: argparse.Namespace) -> None:
    from .acceptance.report import acceptance_report
    from .acceptance.run import run_acceptance

    found = run_acceptance()
    for name, count in found["counts"].items():
        print(f"{name:<11} {count['passed']}/{count['of']}")
    if args.out:
        folder = Path(args.out)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "acceptance.json").write_text(
            json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (folder / "acceptance.md").write_text(
            acceptance_report(found), encoding="utf-8"
        )
        print(f"wrote {folder}")
    print("ACCEPTED" if found["passed"] else "NOT ACCEPTED")
    if not found["passed"]:
        raise Failed("the acceptance found a check that failed")


# ── the command line ─────────────────────────────────────────────────────────


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="skyvault", description=__doc__.split("\n")[0])
    top.add_argument("--version", action="version", version=f"skyvault {__version__}")
    commands = top.add_subparsers(dest="command", required=True)

    def service_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--store", default="sqlite:///skyvault.sqlite")
        sub.add_argument("--redis", default="redis://localhost:6379/0")
        sub.add_argument("--governance", default="governance")

    serve_ = commands.add_parser(
        "serve", help="run the world service, its worker and the UI"
    )
    service_options(serve_)
    serve_.add_argument("--queue", choices=["inprocess", "rq"], default="inprocess")
    serve_.add_argument("--edition", default="internal")
    serve_.add_argument("--host", default="127.0.0.1")
    serve_.add_argument("--port", type=int, default=8000)
    serve_.add_argument("--ui", default=str(UI_BUILD) if UI_BUILD.is_dir() else None)
    serve_.set_defaults(handler=serve)

    worker_ = commands.add_parser("worker", help="run a worker for serve --queue rq")
    service_options(worker_)
    worker_.add_argument("--burst", action="store_true")
    worker_.set_defaults(handler=worker)

    def remote(
        name: str, help_: str, handler: Callable[..., None]
    ) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_)
        sub.add_argument("--url", default=os.environ.get("SKYVAULT_URL", DEFAULT_URL))
        sub.set_defaults(handler=handler, remote=True)
        return sub

    def no_wait(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--no-wait", action="store_true", help="return once queued")

    run_ = remote("run", "run a scenario (<scenario_id>/<version>)", run)
    run_.add_argument("scenario")
    run_.add_argument("--seed", type=int)
    run_.add_argument("--profile")
    no_wait(run_)
    explore_ = remote("explore", "explore where a scenario fails", explore)
    explore_.add_argument("scenario")
    explore_.add_argument("--repeat", type=int)
    no_wait(explore_)
    batch_ = remote("batch", "run a batch request by name", batch)
    batch_.add_argument("name")
    batch_.add_argument("--repeat", type=int)
    no_wait(batch_)
    replay_ = remote("replay", "re-run a finished run and check it reproduces", replay)
    replay_.add_argument("job")
    no_wait(replay_)
    remote("cancel", "cancel a job", cancel).add_argument("job")
    world_ = remote("world", "create, advance or finish a persistent world", world)
    world_.add_argument("action", choices=["create", "advance", "finish"])
    world_.add_argument("target", help="a scenario to create, else a world id")
    world_.add_argument("--ticks", type=int, default=1)
    remote("status", "what the service is doing", status)
    remote("runs", "the runs the UI can show, newest first", runs)
    result_ = remote("result", "a job's result package", result)
    result_.add_argument("job")
    result_.add_argument("--out")
    briefing_ = remote("briefing", "a run's briefing (run id or latest)", briefing)
    briefing_.add_argument("run", nargs="?", default="latest")
    briefing_.add_argument("--format", choices=sorted(REPORT_TYPES), default="md")
    briefing_.add_argument("--out")
    products_ = remote("products", "list the edition's products, or run one", products)
    products_.add_argument("product", nargs="?")

    virtual = commands.add_parser("virtual-test", help="screen an equipment profile")
    virtual.add_argument("profile", help="a committed profile name or a .json file")
    virtual.add_argument("--out")
    virtual.set_defaults(handler=virtual_test_command)
    accept = commands.add_parser("acceptance", help="run the v2.0 acceptance")
    accept.add_argument("--out")
    accept.set_defaults(handler=acceptance)
    return top


def main(argv: Sequence[str] | None = None, http: Any = None) -> int:
    """
    Run one command; 1 with the reason on stderr when it fails. http, an
    httpx.Client, stands in for the connection to --url (tests).
    """
    args = parser().parse_args(argv)
    try:
        if getattr(args, "remote", False):
            args.handler(args, Client(args.url, http))
        else:
            args.handler(args)
    except Failed as error:
        print(f"skyvault: {error}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # skyvault ... | head: the reader has what it wanted
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":  # pragma: no cover - python -m skyvault.cli
    raise SystemExit(main())
