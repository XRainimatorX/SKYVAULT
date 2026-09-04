import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


from skyvault.engine import SkyVaultTacticalReferenceEngine
from skyvault.scenario_loader import load_scenario
from skyvault.timeline import render_timeline


def render_reference_timeline() -> str:
    scenario_path = REPO_ROOT / "data" / "scenarios" / "tactical_reference_001.json"

    scenario = load_scenario(scenario_path)
    engine = SkyVaultTacticalReferenceEngine(scenario)

    result_package = engine.run()

    return render_timeline(
        result_package["scenario_id"],
        result_package["event_memory"],
    )


def test_timeline_output_is_text():
    timeline = render_reference_timeline()

    assert isinstance(timeline, str)
    assert len(timeline.splitlines()) > 1


def test_timeline_has_header_and_scenario_id():
    timeline = render_reference_timeline()

    assert "SKYVAULT Tactical Reference Timeline" in timeline
    assert "tactical_reference_001" in timeline


def test_timeline_has_tick_sections():
    timeline = render_reference_timeline()

    tick_lines = [
        line
        for line in timeline.splitlines()
        if line.startswith("Tick ")
    ]

    assert len(tick_lines) > 0


def test_timeline_has_human_readable_event_lines():
    timeline = render_reference_timeline()

    phrases = [
        "selected",
        "moved from",
        "successfully attacked",
        "but missed",
        "was destroyed by",
        "Scenario Ended",
    ]

    matched = [phrase for phrase in phrases if phrase in timeline]

    assert len(matched) > 0

    assert "Scenario Ended" in timeline
    assert "selected" in timeline


def test_timeline_uses_entity_names_not_raw_ids():
    timeline = render_reference_timeline()

    assert "Red Rifleman" in timeline
    assert "Blue Rifleman" in timeline
    assert "red_001" not in timeline


def test_timeline_can_be_written_to_txt(tmp_path):
    timeline = render_reference_timeline()

    timeline_path = tmp_path / "timeline.txt"
    timeline_path.write_text(timeline, encoding="utf-8")

    assert timeline_path.is_file()
    assert timeline_path.read_text(encoding="utf-8") == timeline
