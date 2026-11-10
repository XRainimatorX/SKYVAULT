import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultEngine
from skyvault.scenario_loader import load_scenario

# The nested shape of Formal Spec section 7.2, adopted by ADR 003.
TOP_LEVEL_FIELDS = {
    "event_id",
    "time",
    "event_type",
    "source",
    "target_entity_id",
    "affected",
    "before_state",
    "after_state",
    "causal_links",
    "evaluation_relevance",
    "data",
    "tags",
}


def run_reference_scenario() -> dict:
    scenario_path = (
        REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"
    )

    scenario = load_scenario(scenario_path)
    engine = SkyVaultEngine(scenario)

    return engine.run()


def events_of_type(events: list[dict], event_type: str) -> list[dict]:
    return [event for event in events if event["event_type"] == event_type]


def test_every_event_has_the_nested_event_shape():
    result_package = run_reference_scenario()

    events = result_package["event_memory"]

    assert len(events) > 0

    for event in events:
        assert set(event) == TOP_LEVEL_FIELDS

        assert set(event["source"]) == {"actor_id", "system_id", "action_id"}
        assert set(event["affected"]) == {"entities", "locations", "resources", "risks"}

        assert isinstance(event["affected"]["entities"], list)
        assert isinstance(event["affected"]["locations"], list)
        assert isinstance(event["affected"]["resources"], list)
        assert isinstance(event["affected"]["risks"], list)
        assert isinstance(event["before_state"], dict)
        assert isinstance(event["after_state"], dict)
        assert isinstance(event["data"], dict)
        assert isinstance(event["tags"], list)

        assert "caused_by" in event["causal_links"]
        assert "caused_events" in event["causal_links"]

        assert "affects_success" in event["evaluation_relevance"]
        assert "affects_cost" in event["evaluation_relevance"]
        assert "affects_risk" in event["evaluation_relevance"]


def test_move_event_has_meaningful_before_and_after_state():
    result_package = run_reference_scenario()

    move_events = events_of_type(result_package["event_memory"], "MOVE")

    assert len(move_events) > 0

    for event in move_events:
        assert event["before_state"] != {}
        assert event["after_state"] != {}
        assert event["before_state"] != event["after_state"]
        assert event["before_state"]["position"] != event["after_state"]["position"]
        assert event["affected"]["entities"] == [event["source"]["actor_id"]]
        assert len(event["affected"]["locations"]) > 0


def test_attack_event_has_meaningful_before_and_after_state():
    result_package = run_reference_scenario()

    attack_events = events_of_type(result_package["event_memory"], "ATTACK")

    assert len(attack_events) > 0

    for event in attack_events:
        assert event["before_state"] != {}
        assert event["after_state"] != {}
        assert event["before_state"] != event["after_state"]

        assert "hp_before" in event["data"]
        assert "hp_after" in event["data"]

        hp_before = event["before_state"]["state"]["hp"]
        hp_after = event["after_state"]["state"]["hp"]

        assert event["data"]["hp_before"] == hp_before
        assert event["data"]["hp_after"] == hp_after
        assert hp_after < hp_before


def test_entity_destroyed_event_structure():
    result_package = run_reference_scenario()

    destroyed_events = events_of_type(
        result_package["event_memory"],
        "ENTITY_DESTROYED",
    )

    for event in destroyed_events:
        assert len(event["affected"]["entities"]) > 0
        assert event["evaluation_relevance"]["affects_success"] is True
        assert "failure" in event["tags"]
        assert event["data"]["destroyed_entity"] == event["target_entity_id"]


def test_scenario_end_event_exists_with_evaluation_summary():
    result_package = run_reference_scenario()

    end_events = events_of_type(result_package["event_memory"], "SCENARIO_END")

    assert len(end_events) == 1

    event = end_events[0]

    assert "winner_or_result" in event["data"]
    assert event["data"]["winner_or_result"] != ""
    assert event["after_state"] != {}
    assert "entities" in event["after_state"]
    # SCENARIO_END keeps the run-end summary; the package's evaluation_result
    # is that summary plus the Phase 7 verdict, with more key findings
    verdict = result_package["evaluation_result"]
    for key, value in event["data"].items():
        if key == "key_findings":
            assert verdict[key][: len(value)] == value
        else:
            assert verdict[key] == value


def test_events_record_the_system_that_produced_the_action():
    scenario_path = (
        REPO_ROOT / "data" / "scenarios" / "tactical_reference_001" / "v0.1.json"
    )

    scenario = load_scenario(scenario_path)
    engine = SkyVaultEngine(scenario)

    result_package = engine.run()

    assumptions = scenario["world_contract"]["assumption_registry"]
    actor_system_id = assumptions["actor_policy"]

    events = result_package["event_memory"]

    for event in events:
        system_id = event["source"]["system_id"]

        assert system_id is not None

        if event["event_type"] == "SCENARIO_END":
            assert system_id != actor_system_id
        else:
            assert system_id == actor_system_id


def test_world_state_does_not_import_policy():
    world_state_source = (SRC_PATH / "skyvault" / "world_state.py").read_text()

    assert "tactical_reference_policy" not in world_state_source


def test_causal_links_connect_events_from_the_same_action():
    result_package = run_reference_scenario()

    events = result_package["event_memory"]
    events_by_id = {event["event_id"]: event for event in events}

    linked_events = [
        event for event in events if len(event["causal_links"]["caused_by"]) > 0
    ]

    assert len(linked_events) > 0

    for event in linked_events:
        for cause_id in event["causal_links"]["caused_by"]:
            cause = events_by_id[cause_id]

            assert cause["source"]["action_id"] == event["source"]["action_id"]
            assert event["event_id"] in cause["causal_links"]["caused_events"]

    for event in events:
        if event["source"]["action_id"] is None:
            assert event["causal_links"]["caused_by"] == []
            assert event["causal_links"]["caused_events"] == []
