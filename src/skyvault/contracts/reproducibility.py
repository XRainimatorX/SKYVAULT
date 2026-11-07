"""Reproducibility contract = what it takes to rerun a run and get the same result."""

from typing import Any, Literal

from .base import ContractModel, NonEmptyStr, check


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
    Phase 1 defines this contract and nothing produces it yet. event_id and
    action_id are still uuid4 and outside the seed's control, so no run could
    honestly fill output_hash. Phase 8 (Reproducibility) makes ids
    deterministic and starts attaching this to every result package.
    """

    run_id: NonEmptyStr
    scenario_id: NonEmptyStr
    scenario_version: NonEmptyStr
    random_seed_policy: Literal["fixed", "controlled_random", "stochastic"]
    random_seed: int | str | None
    runtime_version: NonEmptyStr
    ruleset_version: NonEmptyStr
    input_hash: NonEmptyStr
    output_hash: NonEmptyStr
    deterministic_replay_available: bool
    run_metadata: RunMetadata


def validate_reproducibility(data: dict[str, Any]) -> dict[str, Any]:
    """Validate reproducibility metadata. Raises ContractError when it breaks."""
    return check(ReproducibilityMetadata, "reproducibility", data)
