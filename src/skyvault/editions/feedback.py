"""Feedback: what a commercial scenario teaches, carried back to the core.

Important:
The flows the products run are already the core's, so improving them
improves the core; what flows back is data. A customer's scenario — a
variant made in the commercial edition — becomes a contribution: the
scenario as the customer had it, its data_provenance naming the edition it
came from, the result of the run that produced it and its training
transitions (Phase 18). import_contribution turns it back into a scenario
the internal core runs as its own: aliases restored to internal names,
the scenario contract checked, the provenance kept.
"""

import copy
import hashlib
import json
import re
from typing import Any

from ..contracts import validate_scenario
from ..engine import SkyVaultTacticalReferenceEngine
from ..training.transitions import build_transitions
from .redact import redact


def _restore(data: Any, edition: dict[str, Any]) -> Any:
    """The reverse of redact: each alias back to the internal name it stands for."""
    table = edition.get("redact") or {}
    if not table:
        return data
    # each alias → the first internal name that maps to it, as written there
    reverse: dict[str, str] = {}
    for name, alias in table.items():
        reverse.setdefault(alias, name)
        snake = re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
        reverse.setdefault(snake, re.sub(r"[ \-]+", "_", name).lower())
    return redact(data, {"redact": reverse})


def contribute(
    scenario: dict[str, Any], edition: dict[str, Any], product: str
) -> dict[str, Any]:
    """
    {contribution_id, source_edition, product, scenario, result, transitions}:
    the customer's scenario, run here, as the commercial edition shows it.
    """
    scenario = copy.deepcopy(scenario)
    sources = list((scenario.get("data_provenance") or {}).get("sources", []))
    sources.append(
        {
            "source_id": f"{edition['edition_id']}:{product}",
            "source_type": "external_data",
            "confidence": 1.0,
            "modified_by": f"{edition['edition_id']} edition",
        }
    )
    scenario["data_provenance"] = {
        **(scenario.get("data_provenance") or {}),
        "scenario_id": scenario["scenario_id"],
        "sources": sources,
    }
    package = SkyVaultTacticalReferenceEngine(copy.deepcopy(scenario)).run()
    contribution = {
        "source_edition": edition["edition_id"],
        "product": product,
        "scenario": scenario,
        "result": {
            "winner_or_result": package["evaluation_result"]["winner_or_result"],
            "overall_score": package["evaluation_result"]["overall_score"],
            "output_hash": package["reproducibility"]["output_hash"],
        },
        "transitions": [t for t in build_transitions(package, scenario)],
    }
    shown = redact(contribution, edition)
    digest = hashlib.sha256(
        json.dumps(shown, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return {"contribution_id": f"contribution_{digest[:12]}", **shown}


def import_contribution(
    contribution: dict[str, Any], edition: dict[str, Any]
) -> dict[str, Any]:
    """The contributed scenario as the internal core runs it (validated)."""
    restored = _restore(contribution["scenario"], edition)
    return validate_scenario(restored)
