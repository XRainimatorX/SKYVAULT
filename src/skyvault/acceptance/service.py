"""One running SKYVAULT for the whole acceptance: the internal edition, in process.

Important:
Every check talks to the same world service over HTTP (FastAPI's test
client, no network): what a system outside would see. Jobs run on this
process's queue; wait() blocks until the queue is idle.
"""

from typing import Any

from ..editions.manifest import load_edition
from ..editions.service import create_edition_service, edition_policy
from ..worldservice.api import in_process_queue
from ..worldservice.governance import load_governance
from ..worldservice.store import SQLiteStore

# the system baseline (Phase 21): a domain scenario, not the Phase 0 slice
BASELINE = "military_urban_001/v0.2"
FINISHED = ("completed", "failed")


class Service:
    """The internal edition's world service, and the calls the checks share."""

    def __init__(self) -> None:
        from fastapi.testclient import TestClient

        edition = load_edition("internal")
        policy = edition_policy(edition, load_governance())
        self.store = SQLiteStore()
        self.queue = in_process_queue(self.store, policy)
        self.client = TestClient(
            create_edition_service(edition, self.store, self.queue, policy)
        )

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.client.post(path, json=body or {})

    def get(self, path: str, **params: Any) -> Any:
        return self.client.get(path, params=params or None)

    def wait(self, timeout: float = 600.0) -> None:
        if not self.queue.wait_idle(timeout):
            raise TimeoutError("the queue did not go idle")

    def job(self, request: dict[str, Any]) -> dict[str, Any]:
        """Submit a job, wait for it, return it as it ended."""
        answer = self.post("/api/jobs", request)
        if answer.status_code != 202:
            raise RuntimeError(f"job refused: {answer.status_code} {answer.json()}")
        self.wait()
        found: dict[str, Any] = self.get(f"/api/jobs/{answer.json()['job_id']}").json()
        return found

    def submit(self, submission: dict[str, Any]) -> dict[str, Any]:
        """An external submission, waited for: {answer, returned}."""
        answer = self.post("/scenario/submit", submission)
        if answer.status_code != 202:
            raise RuntimeError(
                f"submission refused: {answer.status_code} {answer.json()}"
            )
        self.wait()
        body = answer.json()
        returned = (
            self.get(f"/submission/{body['submission_id']}").json()
            if body["submission_id"]
            else None
        )
        return {"answer": body, "returned": returned}

    def world(self, scenario: str = BASELINE) -> str:
        created = self.post("/world/create", {"scenario": scenario})
        if created.status_code != 201:
            raise RuntimeError(f"world refused: {created.json()}")
        world_id: str = created.json()["world_id"]
        return world_id

    def act(self, world_id: str, system: str, action: dict[str, Any]) -> Any:
        order = {
            k: v for k, v in action.items() if k not in ("tick", "actor_id", "system")
        }
        return self.post(
            "/action/submit",
            {
                "world_id": world_id,
                "system": system,
                "tick": action["tick"],
                "actor_id": action["actor_id"],
                "order": order,
            },
        )
