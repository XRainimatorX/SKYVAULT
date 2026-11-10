"""Phase 21: the library — where SKYVAULT finds a scenario or a batch by name."""

import json
import os

from skyvault import library
from skyvault.worldservice.jobs import NotFound, scenario_for


def write(folder, name, data):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_skyvault_s_own_folder_comes_first_then_the_environment_s(
    tmp_path, monkeypatch
):
    first, second = tmp_path / "first", tmp_path / "second"
    mine = write(first, "mine_001/v0.1.json", {"a": 1})
    write(second, "mine_001/v0.1.json", {"a": 2})
    monkeypatch.setenv(
        "SKYVAULT_SCENARIO_PATH", os.pathsep.join([str(first), str(second)])
    )

    folders = library.folders("scenarios")
    found = library.find(library.OWN["scenarios"], "mine_001/v0.1.json")
    own = library.find(library.OWN["scenarios"], "military_urban_001/v0.2.json")

    assert folders == [library.OWN["scenarios"], first, second]
    assert found == mine.resolve()
    assert own == (library.OWN["scenarios"] / "military_urban_001/v0.2.json").resolve()
    assert library.scenario_folder(library.OWN["scenarios"], "mine_001") == (
        (first / "mine_001").resolve()
    )


def test_without_the_environment_only_skyvault_s_own_folders_are_searched(
    monkeypatch,
):
    monkeypatch.delenv("SKYVAULT_SCENARIO_PATH", raising=False)
    monkeypatch.delenv("SKYVAULT_BATCH_PATH", raising=False)

    assert library.folders("scenarios") == [library.OWN["scenarios"]]
    assert library.folders("batches") == [library.OWN["batches"]]
    assert library.find(library.OWN["scenarios"], "tactical_reference_001") is None
    assert library.find(library.OWN["batches"], "military_doctrine.json")


def test_a_name_never_climbs_out_of_the_folder_it_is_found_in(tmp_path, monkeypatch):
    write(tmp_path, "secret.json", {})
    extra = tmp_path / "extra"
    extra.mkdir()
    monkeypatch.setenv("SKYVAULT_SCENARIO_PATH", str(extra))

    assert library.find(library.OWN["scenarios"], "../secret.json") is None
    assert library.find(extra, "../secret.json") is None


def test_a_folder_named_by_its_caller_is_searched_alone(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    write(elsewhere, "mine_001/v0.1.json", {})
    monkeypatch.setenv("SKYVAULT_SCENARIO_PATH", str(elsewhere))
    own_folder_only = tmp_path / "mine"
    own_folder_only.mkdir()

    assert library.search(own_folder_only) == [own_folder_only]
    assert library.find(own_folder_only, "mine_001/v0.1.json") is None
    assert library.scenario_folder(own_folder_only, "x") == own_folder_only / "x"


def test_the_world_service_finds_a_deployment_s_own_scenario(tmp_path, monkeypatch):
    source = library.OWN["scenarios"] / "military_squad_001" / "v0.1.json"
    scenario = json.loads(source.read_text(encoding="utf-8"))
    scenario["scenario_id"] = "site_001"
    write(tmp_path, "site_001/v0.1.json", scenario)
    monkeypatch.setenv("SKYVAULT_SCENARIO_PATH", str(tmp_path))

    assert scenario_for({"scenario": "site_001/v0.1"})["scenario_id"] == "site_001"
    monkeypatch.delenv("SKYVAULT_SCENARIO_PATH")
    try:
        scenario_for({"scenario": "site_001/v0.1"})
    except NotFound as error:
        assert "nothing named 'site_001/v0.1' in the scenarios library" in str(error)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("found a scenario outside the library")
