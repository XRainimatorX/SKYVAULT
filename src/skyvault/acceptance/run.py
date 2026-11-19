"""run_acceptance = SKYVAULT 2.0's acceptance, in one session, with evidence.

Important:
Phase 22: SKYVAULT 2.0 is accepted against its two founding documents.
data/v2/spec_acceptance.json lists those criteria — the Formal Spec's nine
hard requirements (§0), its contracts field by field (§2 – §18), its
maturity phases' pass criteria (§21 A – J) and the Definition (Ⅰ – Ⅸ) —
each with the section it comes from. data/v2/acceptance.json lists the
Phase 20 checks, which run first as regression (fifteen acceptance
criteria, fourteen must-haves, the boundary's six "may" and five "may
not"): they make the runs, worlds and conflicts the rest read. All run on
one Service. A check that raises is a failed check with the error as its
evidence; nothing is skipped.
"""

import json
from pathlib import Path
from typing import Any

from .boundary_checks import MAY, MAY_NOT
from .checks import ACCEPTANCE, MUST_HAVE, Check, copy_of
from .service import Service
from .spec_checks import SPEC_CHECKS

LIST = Path(__file__).resolve().parents[3] / "data" / "v2" / "acceptance.json"
SPEC_LIST = LIST.with_name("spec_acceptance.json")
# the founding documents' groups, in the order they are reported
SPEC_GROUPS = ("formal_spec_0", "contracts", "phases", "definition")
REGRESSION = ("acceptance", "must_have", "may", "may_not")


def load_list() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(LIST.read_text(encoding="utf-8"))
    return found


def load_spec_list() -> dict[str, Any]:
    found: dict[str, Any] = json.loads(SPEC_LIST.read_text(encoding="utf-8"))
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
    """
    {formal_spec_0, contracts, phases, definition, regression: {acceptance,
    must_have, boundary: {may, may_not}}, counts, passed}.
    """
    listed, spec = load_list(), load_spec_list()
    service = service or Service()
    shared: dict[str, Any] = {}
    acceptance = _run(listed["acceptance"], ACCEPTANCE, service, shared)
    must_have = _run(listed["must_have"], MUST_HAVE, service, shared)
    may = _run(listed["boundary"]["may"], MAY, service, shared)
    may_not = _run(listed["boundary"]["may_not"], MAY_NOT, service, shared)
    regression = {
        "acceptance": acceptance,
        "must_have": must_have,
        "may": may,
        "may_not": may_not,
    }
    shared["regression"] = {
        row["id"]: row for rows in regression.values() for row in rows
    }
    shared["regression_groups"] = regression
    founding = {
        group: _run(spec[group], SPEC_CHECKS, service, shared) for group in SPEC_GROUPS
    }
    groups = {**founding, **regression}
    counts = {
        name: {"passed": sum(r["passed"] for r in rows), "of": len(rows)}
        for name, rows in groups.items()
    }
    return {
        **founding,
        "regression": {
            "acceptance": acceptance,
            "must_have": must_have,
            "boundary": {"may": may, "may_not": may_not},
        },
        "counts": counts,
        "passed": all(c["passed"] == c["of"] for c in counts.values()),
    }
