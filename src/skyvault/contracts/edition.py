"""Edition contract = one face of SKYVAULT: what it mounts, runs and shows (Phase 19).

Important:
An edition selects from the one core, it never forks it. systems are the
external system adapters it takes submissions from (none: the external
interface is not mounted); domains, job_kinds and products are what it
runs; decision_authorities decide its handoffs; redact maps every internal
name to the alias its responses use instead (empty: responses are the
core's own).
"""

from typing import Any, Literal

from pydantic import Field

from .base import Authority, ContractModel, NonEmptyStr, check
from .job import JobKind

System = Literal[
    "NEXUS",
    "STARTX",
    "TAC_ANGEL",
    "EIDEN_01",
    "AEROGRID",
    "SKYFOX",
    "HADES",
    "CYBERHOUND",
    "STAR_GUARD",
]


class Edition(ContractModel):
    edition_id: NonEmptyStr
    title: NonEmptyStr
    description: str = ""
    systems: list[System] = Field(default_factory=list)
    domains: list[NonEmptyStr] = Field(default_factory=list)
    job_kinds: list[JobKind] = Field(default_factory=list)
    products: list[NonEmptyStr] = Field(default_factory=list)
    decision_authorities: list[Authority] = Field(min_length=1)
    redact: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)


def validate_edition(data: dict[str, Any]) -> dict[str, Any]:
    """An edition manifest, or ContractError listing every violation."""
    return check(Edition, "edition", data)
