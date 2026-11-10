"""run_acceptance = Full SKYVAULT v2.0's acceptance, in one session, with evidence.

Important:
data/v2/acceptance.json lists what is checked (its ids and titles); the
checks run in this order on one Service: the fifteen acceptance criteria
(they make the runs, worlds and conflicts the rest read), the fourteen
must-haves, then the boundary's six "may" and five "may not". A check that
raises is a failed check with the error as its evidence; nothing is skipped.
"""

import json
from pathlib import Path
from typing import Any

from .boundary_checks import MAY, MAY_NOT
from .checks import ACCEPTANCE, MUST_HAVE, Check, copy_of
from .service import Service

LIST = Path(__file__).resolve().parents[3] / "data" / "v2" / "acceptance.json"


def load_list() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(LIST.read_text(encoding="utf-8"))
    return found


def _run(
    items: list[dict[str, str]],
    checks: dict[str, Check],
    service: Service,
    shared: dict[str, Any],
) -> list[dict[str, Any]]:
    results = []
    for item in items:
        check = checks.get(item["id"])
        try:
            if check is None:
                raise LookupError(f"no check for {item['id']!r}")
            outcome = check(service, shared)
            passed, evidence = bool(outcome["passed"]), copy_of(outcome["evidence"])
        except Exception as error:  # a check that breaks is a check that fails
            passed, evidence = False, {"error": f"{type(error).__name__}: {error}"}
        results.append({**item, "passed": passed, "evidence": evidence})
    return results


def run_acceptance(service: Service | None = None) -> dict[str, Any]:
    """{acceptance, must_have, boundary: {may, may_not}, passed, counts}."""
    listed = load_list()
    service = service or Service()
    shared: dict[str, Any] = {}
    acceptance = _run(listed["acceptance"], ACCEPTANCE, service, shared)
    must_have = _run(listed["must_have"], MUST_HAVE, service, shared)
    may = _run(listed["boundary"]["may"], MAY, service, shared)
    may_not = _run(listed["boundary"]["may_not"], MAY_NOT, service, shared)
    groups = {
        "acceptance": acceptance,
        "must_have": must_have,
        "may": may,
        "may_not": may_not,
    }
    counts = {
        name: {"passed": sum(r["passed"] for r in rows), "of": len(rows)}
        for name, rows in groups.items()
    }
    return {
        "acceptance": acceptance,
        "must_have": must_have,
        "boundary": {"may": may, "may_not": may_not},
        "counts": counts,
        "passed": all(c["passed"] == c["of"] for c in counts.values()),
    }
