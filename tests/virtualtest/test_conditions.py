"""Phase 22: SKYVAULT Definition VII — what equipment must be tested under."""

import json
from pathlib import Path

from skyvault.failure.variables import FAILURE_VARIABLES
from skyvault.virtualtest.conditions import ENGINEERING, TACTICAL, TEST_CONDITIONS
from skyvault.virtualtest.physics import CHECKS
from skyvault.virtualtest.profile import load_rules
from skyvault.virtualtest.stress import explore_equipment

PROFILES = Path(__file__).resolve().parents[2] / "data" / "virtualtest" / "profiles"


def test_every_kind_the_definition_lists_has_its_conditions():
    assert set(TEST_CONDITIONS) == {
        "EXO / PAX",
        "MSX / 新 MS",
        "載具",
        "感測器",
        "能源系統",
        "維修流程",
        "操作流程",
    }
    assert {"樓梯", "泥地", "長時間行動"} <= set(TEST_CONDITIONS["EXO / PAX"])
    assert {"跌倒", "碰撞"} <= set(TEST_CONDITIONS["MSX / 新 MS"])
    assert {"夜間", "煙霧"} <= set(TEST_CONDITIONS["感測器"])
    assert "錯誤率" in TEST_CONDITIONS["操作流程"]


def test_every_condition_names_something_skyvault_runs():
    rules = load_rules()
    stresses = set(rules["stress"]["conditions"])
    scenarios = set(rules["tactical"]["scenarios"])
    for kind in TEST_CONDITIONS.values():
        for item, tests in kind.items():
            assert tests, item
            for test in tests:
                ((how, name),) = test.items()
                known = {
                    "stress": stresses,
                    "check": set(CHECKS) | set(ENGINEERING),
                    "variable": set(FAILURE_VARIABLES),
                    "tactical": set(TACTICAL) | scenarios,
                }[how]
                assert name in known, (item, how, name)


def test_stairs_and_impact_are_stress_conditions_of_the_virtual_test():
    rules = load_rules()
    profile = json.loads((PROFILES / "exo_test_001.json").read_text(encoding="utf-8"))
    found = explore_equipment(profile, rules)
    points = {p["condition"]: p for p in found["failure_points"]}
    assert {"stairs", "impact"} <= set(points)
    # a narrower footing and a harder knock break stability and the joints
    assert set(points["stairs"]["breaks"]) <= {"stability"}
    assert set(points["impact"]["breaks"]) <= {"joint_load"}
    assert (
        points["stairs"]["level"] is not None or points["impact"]["level"] is not None
    )
