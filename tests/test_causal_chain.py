import json
from pathlib import Path

#this checks that causal_chain.py actually created the json
def test_causal_chain_output_exists():
    path = Path("output/causal_chain.json")
    assert path.exists()

#to check if the overall structure is correct
def test_causal_chain_has_required_keys():
    with open("output/causal_chain.json", "r") as f:
        causal_chain = json.load(f)

    #check if causal_chain.py contains scenario id and chains
    assert "scenario_id" in causal_chain
    assert "chains" in causal_chain
    #check if chains is a list
    assert isinstance(causal_chain["chains"], list)

#to check individual chain in chains
def test_each_chain_has_required_fields():
    with open("output/causal_chain.json", "r") as f:
        causal_chain = json.load(f)

    for chain in causal_chain["chains"]:
        assert "source_action_id" in chain
        assert "events" in chain
        assert "event_types" in chain
        assert "summary" in chain
        assert isinstance(chain["events"], list)
        assert isinstance(chain["event_types"], list)