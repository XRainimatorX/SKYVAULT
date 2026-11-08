"""Reproducibility contract = what it takes to rerun a run and get the same result."""

from typing import Annotated, Any, Literal

from pydantic import Field

from .base import ContractModel, NonEmptyStr, check

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class RunMetadata(ContractModel):
    """When and where a run happened."""

    started_at: NonEmptyStr
    ended_at: NonEmptyStr
    compute_profile: str = ""
    operator_system: str = ""


class ReproducibilityMetadata(ContractModel):
    """
    Reproducibility Metadata = Formal Spec section 12.2.

    Important:
    Every result package carries this from Phase 8 on. input_hash covers the
    scenario and the evaluation profile; output_hash covers the whole result
    package except this block, which records when the run happened and so can
    never repeat. Two runs with the same output_hash produced the same result.

    random_seed is null for a stochastic run, which cannot be replayed.
    """

    run_id: NonEmptyStr
    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    random_seed_policy: Literal["fixed", "controlled_random", "stochastic"]
    random_seed: int | None
    runtime_version: NonEmptyStr
    ruleset_version: NonEmptyStr
    input_hash: SHA256
    output_hash: SHA256
    deterministic_replay_available: bool
    run_metadata: RunMetadata


def validate_reproducibility(data: dict[str, Any]) -> dict[str, Any]:
    """Validate reproducibility metadata. Raises ContractError when it breaks."""
    return check(ReproducibilityMetadata, "reproducibility", data)
