"""Editions as data: which face of SKYVAULT a deployment shows (Phase 19).

Important:
data/editions/<edition_id>.json, validated against the edition contract.
internal is the core as it is; commercial is the clean shell. Both run the
same core: an edition only says what is mounted, run and shown.
"""

import json
from pathlib import Path
from typing import Any, Literal

from ..contracts import validate_edition

EDITIONS = Path(__file__).resolve().parents[3] / "data" / "editions"
FIELDS = {
    "system": "systems",
    "domain": "domains",
    "job_kind": "job_kinds",
    "product": "products",
}
What = Literal["system", "domain", "job_kind", "product"]


def edition_ids() -> list[str]:
    """Every committed edition (products.json is the product catalogue)."""
    return sorted(p.stem for p in EDITIONS.glob("*.json") if p.stem != "products")


def load_edition(edition_id: str) -> dict[str, Any]:
    """The edition, validated; ValueError for one that is not committed."""
    if edition_id not in edition_ids():
        known = ", ".join(edition_ids())
        raise ValueError(f"unknown edition {edition_id!r} (known: {known})")
    data = json.loads((EDITIONS / f"{edition_id}.json").read_text(encoding="utf-8"))
    return validate_edition(data)


def allows(edition: dict[str, Any], what: What, name: str) -> bool:
    """Whether the edition mounts / runs this system, domain, job kind or product."""
    return name in edition.get(FIELDS[what], [])


def public(edition: dict[str, Any]) -> dict[str, Any]:
    """What a client may see of its edition: never the redaction table."""
    return {
        k: edition[k]
        for k in ("edition_id", "title", "domains", "job_kinds", "products")
        if k in edition
    }
