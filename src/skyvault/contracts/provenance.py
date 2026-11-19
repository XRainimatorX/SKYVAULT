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
    Data Provenance = Formal Spec sections 11.3 and 3.3.

    Important:
    Section 11.3 gives sources (each with type, time, confidence, version and
    who modified it), reliability_notes and missing_data; section 3.3 writes
    the same block inside a scenario with timestamps, confidence,
    modified_by and input_version beside the sources. Both sets of fields are
    here, so either section's document validates. A world contract's
    provenance is the flatter section 2.3 block (contracts.world).
    """

    scenario_id: str | None = None
    sources: list[ProvenanceSource] = Field(default_factory=list)
    timestamps: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, Probability] = Field(default_factory=dict)
    modified_by: str = ""
    input_version: str = ""
    reliability_notes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


def validate_data_provenance(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a data provenance record. Raises ContractError when it breaks."""
    return check(DataProvenance, "data_provenance", data)
