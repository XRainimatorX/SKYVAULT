import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.action import Action
from skyvault.contracts import (
    ContractError,
    validate_action,
    validate_consequence,
    validate_entity,
    validate_event,
)
from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario

REFERENCE_SCENARIO = (
    REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"
)


def fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as file:
        return json.load(file)


def run_reference_scenario() -> dict:
    return SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO)).run()


# ── acceptance criterion 2: an action without actor_id is rejected ──────────


def test_action_without_actor_id_is_rejected():
    with pytest.raises(ContractError) as caught:
        validate_action(fixture("action_missing_actor_id"))

    assert caught.value.contract == "action"
    assert any(error.startswith("actor_id:") for error in caught.value.errors)


def test_action_with_empty_actor_id_is_rejected():
    action = fixture("action_valid")
    action["actor_id"] = ""

    with pytest.raises(ContractError):
        validate_action(action)


def test_valid_action_passes_and_keeps_its_shape():
    action = fixture("action_valid")

    assert validate_action(action) == action


def test_engine_refuses_a_malformed_action_from_the_policy():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO))

    def broken_policy(world, actor):
        return Action(action_id="action_broken", actor_id="", action_type="move")

    engine.policy.decide_action = broken_policy

    with pytest.raises(ContractError):
        engine.run()


# ── acceptance criterion 3: an event must have before_state / after_state ───


def test_event_without_before_state_is_rejected():
    with pytest.raises(ContractError) as caught:
        validate_event(fixture("event_missing_before_state"))

    assert any(error.startswith("before_state:") for error in caught.value.errors)


def test_event_without_after_state_is_rejected():
    event = fixture("event_valid")
    del event["after_state"]

    with pytest.raises(ContractError) as caught:
        validate_event(event)

    assert any(error.startswith("after_state:") for error in caught.value.errors)


def test_contract_error_reports_every_violation_at_once():
    event = fixture("event_valid")
    del event["before_state"]
    del event["after_state"]

    with pytest.raises(ContractError) as caught:
        validate_event(event)

    fields = {error.split(":")[0] for error in caught.value.errors}
    assert fields == {"before_state", "after_state"}


def test_event_rejects_unknown_event_type():
    event = fixture("event_valid")
    event["event_type"] = "TELEPORT"

    with pytest.raises(ContractError):
        validate_event(event)


def test_event_rejects_the_old_flat_shape():
    event = fixture("event_valid")
    event["actor_id"] = event["source"].pop("actor_id")

    with pytest.raises(ContractError):
        validate_event(event)


def test_valid_event_passes_and_keeps_its_shape():
    event = fixture("event_valid")

    assert validate_event(event) == event


def test_every_event_of_a_real_run_satisfies_the_contract():
    events = run_reference_scenario()["event_memory"]

    assert len(events) == 97

    for event in events:
        assert validate_event(copy.deepcopy(event)) == event


# ── entity and consequence ───────────────────────────────────────────────────


def test_every_scenario_entity_satisfies_the_entity_contract():
    scenario = load_scenario(REFERENCE_SCENARIO)

    for entity in scenario["entities"]:
        assert validate_entity(entity) == entity


def test_entity_position_must_be_two_integers():
    entity = load_scenario(REFERENCE_SCENARIO)["entities"][0]
    entity["position"] = [1, 2, 3]

    with pytest.raises(ContractError):
        validate_entity(entity)


def test_consequence_requires_every_section_6_part():
    with pytest.raises(ContractError) as caught:
        validate_consequence({"action_id": "action_x"})

    fields = {error.split(":")[0] for error in caught.value.errors}
    assert fields == {
        "accepted",
        "reason",
        "direct_effects",
        "secondary_effects",
        "chain_reactions",
        "evaluation_impact",
    }


def test_consequence_fixture_passes_and_keeps_its_shape():
    consequence = fixture("consequence_valid")

    assert validate_consequence(consequence) == consequence


def test_consequence_produced_by_the_engine_satisfies_the_contract():
    engine = SkyVaultTacticalReferenceEngine(load_scenario(REFERENCE_SCENARIO))
    actor = engine.world.get_entity("red_001")
    action = engine.policy.decide_action(engine.world, actor)
    consequence = engine.resolver.execute(engine.world, action)

    recorded = validate_consequence(consequence.to_dict())
    assert recorded["accepted"] is True
    assert recorded["direct_effects"]["entity_changes"][0]["event_type"] == "MOVE"


# ── layering ─────────────────────────────────────────────────────────────────


def import_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("import ", "from "))
    ]


def test_contracts_import_nothing_else_from_skyvault():
    for path in (SRC_PATH / "skyvault" / "contracts").glob("*.py"):
        for line in import_lines(path):
            assert not line.startswith("from .."), (path.name, line)
            assert "skyvault" not in line, (path.name, line)


def test_exporters_do_not_import_contracts():
    for name in ("timeline", "replay", "entity_history", "causal_chain"):
        for line in import_lines(SRC_PATH / "skyvault" / f"{name}.py"):
            assert "contracts" not in line, (name, line)
