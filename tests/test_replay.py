import json
from pathlib import Path

#this checks that replay.py actually created the json
def test_replay_output_exists():
    path = Path("output/replay_state_at_tick.json")
    assert path.exists()

#to check if the overall structure is correct
def test_replay_has_required_keys():
    with open("output/replay_state_at_tick.json", "r") as f:
        replay = json.load(f)

    assert "scenario_id" in replay
    assert "states" in replay
    assert "0" in replay["states"]
    assert "final" in replay["states"]

#to check if every tick contains description and world_state
def test_replay_each_tick_has_description_and_world_state():
    with open("output/replay_state_at_tick.json", "r") as f:
        replay = json.load(f)

    for tick, state in replay["states"].items():
        assert "description" in state
        assert "world_state" in state