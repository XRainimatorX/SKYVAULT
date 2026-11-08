"""create_edition_service = the world service an edition shows its customers.

Important:
The same world service (Phase 11) over the same core, assembled for one
edition:

- the external interface (Phase 12) is mounted only when the edition names
  systems, and then takes submissions from those systems only — an
  interface left out is not removed: naming a system mounts it again
- every job is asked first whether the edition runs its kind and its
  scenario's domain (403 not_licensed otherwise)
- handoffs name the edition's decision authorities
- /api/edition says which edition this is (never its redaction table);
  /api/products lists its products and /api/products/{id} runs one
- every JSON response passes through the edition's redaction, so no
  internal name reaches a commercial client

The internal edition is the world service exactly as it was.
"""

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response

from ..worldservice.api import create_world_service, in_process_queue
from ..worldservice.jobs import scenario_for
from ..worldservice.queues import JobQueue
from ..worldservice.store import JobStore
from .manifest import allows, public
from .products import catalogue, run_product
from .redact import redact


def edition_policy(edition: dict[str, Any], policy: dict[str, Any]) -> dict:
    """The governance policy with the edition's decision authorities."""
    return {**policy, "decision_authorities": list(edition["decision_authorities"])}


def gate_for(edition: dict[str, Any]) -> Any:
    """Refuses (PermissionError) a job of a kind or domain the edition does not run."""

    def gate(request: dict[str, Any]) -> None:
        kind = request.get("kind")
        if not allows(edition, "job_kind", str(kind)):
            raise PermissionError(
                f"the {edition['edition_id']} edition does not run {kind} jobs"
            )
        if request.get("scenario"):
            domain = scenario_for(request).get("domain")
            if domain and not allows(edition, "domain", domain):
                raise PermissionError(
                    f"the {edition['edition_id']} edition does not run the "
                    f"{domain} domain"
                )

    return gate


def create_edition_service(
    edition: dict[str, Any],
    store: JobStore,
    queue: JobQueue | None,
    policy: dict[str, Any],
) -> FastAPI:
    """
    The world service for one edition (see the module doc).

    queue None builds this process's queue under the edition's policy; a
    queue given here must already run its jobs under edition_policy(...),
    or its handoffs keep the default authorities.
    """
    policy = edition_policy(edition, policy)
    if queue is None:
        queue = in_process_queue(store, policy)
    app = create_world_service(
        store, queue, policy, external_routes=False, gate=gate_for(edition)
    )
    app.title = f"{edition['title']} world service"
    if edition["systems"]:
        from ..interface.api import add_external_routes

        add_external_routes(app, store, queue, policy, systems=edition["systems"])

    @app.get("/api/edition")
    def which() -> dict[str, Any]:
        return public(edition)

    @app.get("/api/products")
    def products() -> list[dict[str, str]]:
        entries = catalogue()
        return [
            {
                "product": p,
                "title": entries[p]["title"],
                "question": entries[p]["question"],
            }
            for p in edition["products"]
        ]

    @app.post("/api/products/{product_id}")
    def product(product_id: str) -> dict[str, Any]:
        if product_id not in catalogue():
            raise HTTPException(404, {"reason": "not_found", "detail": product_id})
        try:
            return run_product(product_id, edition, repeats=2)
        except PermissionError as error:
            raise HTTPException(
                403, {"reason": "not_licensed", "detail": str(error)}
            ) from None

    if edition.get("redact"):

        @app.middleware("http")
        async def redacted(request: Request, call_next: Any) -> Response:
            response = await call_next(request)
            if "application/json" not in response.headers.get("content-type", ""):
                return response
            body = b"".join([chunk async for chunk in response.body_iterator])
            data = redact(json.loads(body), edition)
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in ("content-length", "content-type")
            }
            return Response(
                json.dumps(data, ensure_ascii=False),
                status_code=response.status_code,
                headers=headers,
                media_type="application/json",
            )

    return app
