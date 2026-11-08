"""Phase 8 acceptance 3: every result package says where it came from."""

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


import skyvault
from skyvault.contracts import (
    ContractError,
    validate_reproducibility,
    validate_scenario,
)
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.reproducibility import (
    RUNTIME_VERSION,
    input_hash,
    output_hash,
    ruleset_version,
    seed_policy,
)
from skyvault.scenario_loader import load_evaluation_profile, load_scenario

SCENARIOS = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001"
PROFILES = REPO_ROOT / "data" / "evaluation_profiles"


def scenario(version: str = "v0.1") -> dict:
    return load_scenario(SCENARIOS / f"{version}.json")


def run(chosen=None, profile=None) -> dict:
    return SkyVaultTacticalReferenceEngine(chosen or scenario(), profile).run()


def test_every_package_carries_a_valid_reproducibility_block():
    package = run()
    block = package["reproducibility"]

    validate_reproducibility(block)
    assert block["scenario_id"] == "tactical_reference_001"
    assert block["scenario_version"] == "v0.1"
    assert block["random_seed_policy"] == "fixed"
    assert block["random_seed"] == 42
    assert block["deterministic_replay_available"] is True
    assert re.fullmatch(r"run_\d{8}T\d{12}Z_[0-9a-f]{8}", block["run_id"])


def test_the_block_hashes_match_what_was_run_and_produced():
    engine = SkyVaultTacticalReferenceEngine(scenario())
    package = engine.run()
    block = package["reproducibility"]

    assert block["output_hash"] == output_hash(package)
    assert block["input_hash"] == input_hash(engine.scenario, engine.evaluation_profile)
    assert block["run_id"].endswith(block["input_hash"][:8])


def test_two_runs_share_hashes_but_not_run_ids():
    first, second = run(), run()

    for key in ("input_hash", "output_hash", "ruleset_version", "runtime_version"):
        assert first["reproducibility"][key] == second["reproducibility"][key]
    assert first["reproducibility"]["run_id"] != second["reproducibility"]["run_id"]


def test_another_seed_is_another_input_and_another_result():
    reseeded = scenario()
    reseeded["runtime"]["random_seed"] = 7

    a, b = run(), run(reseeded)

    assert a["reproducibility"]["input_hash"] != b["reproducibility"]["input_hash"]
    assert a["reproducibility"]["output_hash"] != b["reproducibility"]["output_hash"]
    assert b["evaluation_result"]["winner_or_result"] == "BLUE_survived"


def test_another_profile_is_another_input_with_the_same_events():
    tactical = load_evaluation_profile(PROFILES / "tactical.json")

    a, b = run(), run(profile=tactical)

    assert a["reproducibility"]["input_hash"] != b["reproducibility"]["input_hash"]
    assert a["reproducibility"]["output_hash"] != b["reproducibility"]["output_hash"]
    assert a["event_memory"] == b["event_memory"]


# ── versions ─────────────────────────────────────────────────────────────────


def test_the_runtime_version_is_the_package_version():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    declared = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE).group(1)

    # One version, kept in two files, recorded in every package
    assert RUNTIME_VERSION == skyvault.__version__ == declared
    assert run()["reproducibility"]["runtime_version"] == declared
    assert re.fullmatch(r"0\.\d+\.0", declared)


def test_the_ruleset_version_moves_with_rules_not_with_data():
    base = scenario()
    military = ["attack", "move", "observe", "repair", "supply"]
    reruled = scenario()
    reruled["world_contract"]["rule_set"] = {"action_costs": {"move": {"fuel": 1}}}
    redata = scenario()
    redata["entities"][0]["state"]["hp"] = 1

    version = ruleset_version(base, military)

    assert re.fullmatch(r"rules-[0-9a-f]{12}", version)
    assert ruleset_version(redata, military) == version
    assert ruleset_version(base, list(reversed(military))) == version
    assert ruleset_version(reruled, military) != version
    assert ruleset_version(base, military + ["wait"]) != version


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [
        ({"random_seed": 42}, ("fixed", 42, True)),
        (
            {"random_seed": 3, "random_seed_policy": "controlled_random"},
            ("controlled_random", 3, True),
        ),
        (
            {"random_seed": 3, "random_seed_policy": "stochastic"},
            ("stochastic", None, False),
        ),
    ],
)
def test_seed_policy(runtime, expected):
    assert seed_policy(runtime) == expected


def test_a_stochastic_run_records_no_seed_and_cannot_be_replayed():
    stochastic = scenario()
    stochastic["runtime"]["random_seed_policy"] = "stochastic"

    block = run(stochastic)["reproducibility"]

    assert block["random_seed"] is None
    assert block["deterministic_replay_available"] is False


# ── scenario version control ─────────────────────────────────────────────────


def test_version_control_must_name_the_scenarios_own_version():
    tagged = scenario()
    tagged["version_control"] = {
        "version": "v9.9",
        "parent_version": None,
        "changed_from_previous": {},
        "change_reason": "",
    }

    with pytest.raises(ContractError, match="is not scenario_version"):
        validate_scenario(tagged)


def test_a_scenario_written_for_schema_0_4_is_rejected():
    old = scenario()
    old["schema_version"] = "0.4"

    with pytest.raises(ContractError):
        validate_scenario(old)
