"""Small hand-made military worlds for rule and policy tests."""

import copy
import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from skyvault.actions import ActionContext, ActionResolver
from skyvault.domains.military import build_scenario, load_profiles
from skyvault.domains.military.handlers import military_handlers
from skyvault.runtime.world import create_world

SPECS = REPO_ROOT / "data" / "domains" / "military" / "scenarios"


class FixedRng(random.Random):
    """random() always returns value; choice() takes the first option."""

    def __init__(self, value=0.0):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value

    def choice(self, seq):
        return seq[0]


@pytest.fixture(scope="session")
def profiles():
    return load_profiles()


def spec(red, blue, rows=None, red_side=None, blue_side=None):
    """A spec with units given as (unit_type, [x, y]) pairs."""

    def side(units, extra):
        base = {
            "doctrine": "aggressive",
            "command": "immediate",
            "mission": {"type": "destroy"},
            "groups": [
                {"name": f"G{i}", "formation": "line", "anchor": cell, "units": [kind]}
                for i, (kind, cell) in enumerate(units)
            ],
        }
        base.update(extra or {})
        return base

    return {
        "scenario_id": "military_test",
        "scenario_version": "v0",
        "max_ticks": 10,
        "random_seed": 7,
        "map": rows
        or [
            "........",
            "..ff....",
            "..^.....",
            "........",
        ],
        "factions": {"RED": side(red, red_side), "BLUE": side(blue, blue_side)},
    }


@pytest.fixture
def make_world(profiles):
    def make(red, blue, rng_value=0.0, **kwargs):
        scenario = build_scenario(spec(red, blue, **kwargs), profiles)
        world = create_world(scenario)
        resolver = ActionResolver(
            military_handlers(), ActionContext(rng=FixedRng(rng_value))
        )
        return scenario, world, resolver

    return make


def load_spec(name):
    with (SPECS / f"{name}.json").open(encoding="utf-8") as file:
        return copy.deepcopy(json.load(file))
