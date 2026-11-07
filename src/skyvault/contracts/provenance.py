"""Data Provenance contract = where scenario data came from, and how reliable it is."""

from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, Probability, check

SourceType = Literal[
    "EIDEN_01",
    "STARTX",
    "manual_input",
    "external_data",
    "historical_record",
]


class ProvenanceSource(ContractModel):
    """One source of scenario data."""

    source_id: NonEmptyStr
    source_type: SourceType
    timestamp: str = ""
    confidence: Probability
    version: str = ""
    modified_by: str = ""


class DataProvenance(ContractModel):
    """
    Data Provenance = Formal Spec section 11.3.

    Important:
    Section 2.3 sketches world_contract.data_provenance as a flat block. No
    scenario carries provenance yet, so there is no existing shape to keep;
    both places use this dedicated section 11.3 contract. See ADR 004.
    """

    scenario_id: str | None = None
    sources: list[ProvenanceSource] = Field(default_factory=list)
    reliability_notes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


def validate_data_provenance(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a data provenance record. Raises ContractError when it breaks."""
    return check(DataProvenance, "data_provenance", data)
