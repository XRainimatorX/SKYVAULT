"""Conditions = SKYVAULT Definition VII "可以測什麼", item by item, and what tests each.

Important:
The Definition lists, per kind of equipment, the conditions it must be
tested under. Each maps to where SKYVAULT tests it:

    stress     a virtual test stress condition (rules.json stress): the
               physics and engineering judged again with one quantity moved
    check      a physical check (physics.CHECKS) or an engineering component
               (engineering.py: material, maintenance, parts, supply, repair)
    variable   a failure variable on the tactical runs the equipment joins
    tactical   the tactical runs (Phase 16): a scenario the equipment joins,
               or what they read from the profile (terrain_access,
               concealment, operator_fatigue, logistics_burden)

A test holds every entry to something that exists. What physics-lite
cannot say (a CAD, CAE or FEA question) is out of scope by the Definition's
own boundary, and external.py says when to hand it over.
"""

from typing import Any

TEST_CONDITIONS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "EXO / PAX": {
        "城市": [{"tactical": "military_urban_001"}],
        "山地": [{"tactical": "military_mountain_001"}],
        "樓梯": [{"stress": "stairs"}, {"check": "stability"}],
        "泥地": [{"stress": "soft_ground"}, {"check": "ground_pressure"}],
        "長時間行動": [
            {"stress": "extended_mission"},
            {"check": "energy"},
            {"variable": "endurance_shortfall"},
        ],
    },
    "MSX / 新 MS": {
        "重心": [{"check": "stability"}],
        "跌倒": [{"stress": "stairs"}, {"check": "stability"}],
        "碰撞": [{"stress": "impact"}, {"check": "joint_load"}],
        "轉向": [{"check": "scale"}],
        "障礙通行": [{"check": "ground_pressure"}, {"tactical": "terrain_access"}],
    },
    "載具": {
        "是否能運載 PAX / MSX": [
            {"stress": "payload"},
            {"tactical": "logistics_burden"},
        ],
        "是否適應地形": [{"stress": "soft_ground"}, {"tactical": "terrain_access"}],
    },
    "感測器": {
        "夜間": [{"variable": "sensor_failure"}],
        "煙霧": [{"variable": "sensor_failure"}, {"variable": "weather_degradation"}],
        "雨雪": [{"variable": "weather_degradation"}],
        "遮蔽環境": [{"tactical": "concealment"}],
    },
    "能源系統": {
        "功率": [{"check": "energy"}],
        "續航": [{"stress": "extended_mission"}, {"variable": "endurance_shortfall"}],
        "散熱": [{"stress": "heat"}, {"check": "heat"}],
        "補給需求": [{"stress": "supply_disruption"}, {"check": "maintenance"}],
    },
    "維修流程": {
        "戰場維修時間": [{"stress": "supply_disruption"}, {"check": "maintenance"}],
        "零件替換": [{"check": "parts"}],
        "後勤負擔": [{"check": "supply"}, {"tactical": "logistics_burden"}],
    },
    "操作流程": {
        "操作員疲勞": [{"tactical": "operator_fatigue"}],
        "人機工效": [{"tactical": "operator_fatigue"}],
        "錯誤率": [{"variable": "communication_failure"}],
    },
}


TACTICAL = ("terrain_access", "concealment", "operator_fatigue", "logistics_burden")
ENGINEERING = ("material", "maintenance", "parts", "supply", "repair")
