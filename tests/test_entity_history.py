import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.entity_history import build_entity_history
from skyvault.scenario_loader import load_scenario

RECORD_FIELDS = [
    "time",
    "event_type",
    "role_in_event",
    "event_id",
    "source_action_id",
    "before_state",
    "after_state",
    "data",
    "tags",
]


def build_reference_entity_history() -> dict:
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    return build_entity_history(
        result_package["initial_world_state"],
        result_package["event_memory"],
    )


def test_entity_history_structure():
    entity_history = build_reference_entity_history()

    assert isinstance(entity_history, dict)
    assert len(entity_history) > 0


def test_entity_history_has_red_and_blue():
    entity_history = build_reference_entity_history()

    factions = {entity["faction"] for entity in entity_history.values()}

    assert "RED" in factions
    assert "BLUE" in factions


def test_each_entity_has_required_fields():
    entity_history = build_reference_entity_history()

    for entity in entity_history.values():
        assert "entity_id" in entity
        assert "name" in entity
        assert "faction" in entity
        assert "history" in entity
        assert len(entity["history"]) > 0


def test_history_includes_initial_state():
    entity_history = build_reference_entity_history()

    for entity in entity_history.values():
        event_types = [record["event_type"] for record in entity["history"]]

        assert "INITIAL_STATE" in event_types
        assert event_types[0] == "INITIAL_STATE"


def test_every_record_has_the_same_shape():
    entity_history = build_reference_entity_history()

    for entity in entity_history.values():
        for record in entity["history"]:
            for field in RECORD_FIELDS:
                assert field in record

            assert isinstance(record["before_state"], dict)
            assert isinstance(record["after_state"], dict)
            assert isinstance(record["data"], dict)
            assert isinstance(record["tags"], list)


def test_history_records_actor_target_and_affected_roles():
    entity_history = build_reference_entity_history()

    roles = {
        record["role_in_event"]
        for entity in entity_history.values()
        for record in entity["history"]
    }

    assert "initial_state" in roles
    assert "actor" in roles
    assert "affected" in roles
    assert "final_state" in roles
