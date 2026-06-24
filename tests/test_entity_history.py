import sys
from pathlib import Path
import json

# Add path to sys.path to avoid path not found error
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# First bring in the output file
entity_dict: dict

entity_path = REPO_ROOT / "output" / "entity_history.json"

with open(entity_path, "r") as f:

    entity_dict = json.loads(f.read())

# Test 1: Basic structure and non-emptiness
def test_structure():

    assert isinstance(entity_dict, dict)
    assert len(entity_dict) > 0

# Test 2: Existence of factions records
def test_factions():

    factions = {}

    for entity in entity_dict.values():

        faction = entity["faction"]
        factions[faction] = None

    assert "RED" in factions
    assert "BLUE" in factions

# Test 3: Entity basic structure
def test_entity_structure():

    for entity in entity_dict.values():

        assert "entity_id" in entity
        assert "name" in entity
        assert "faction" in entity
        assert "history" in entity

# Test 4: Existence of INITIAL_STATE records
def test_initial_state():

    event_types = []

    for entity_data in entity_dict.values():

        history = entity_data["history"]
        
        for record in history:

            event_types.append(record["event_type"])

    assert "INITIAL_STATE" in event_types

# Test 5: Existence of state records
def test_states():

    for entity_data in entity_dict.values():

        history = entity_data["history"]
        
        for record in history:

            assert "initial_state" or "before_state" or "after_state" or "final_state" or "state" in record