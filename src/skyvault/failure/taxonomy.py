"""Taxonomy = Formal Spec 14.2, row by row: what to make fail, and how SKYVAULT does.

Important:
Each class of plan the section names has the ways it must be made to fail.
Each way maps to what tests it here:

    variables   failure variables a failure exploration stresses
    checks      where the failure is judged instead of stressed — a virtual
                test check (Phase 16: a fall is a stability margin, not a
                run) or an anti-gaming check (a local win at strategic cost
                is a judgement of a run, not a stress)

A test checks every variable exists (core or a domain pack) and every check
is one SKYVAULT runs, so this table cannot promise what is not there.
"""

from typing import Any

FAILURE_TAXONOMY: dict[str, dict[str, Any]] = {
    "tactical_plan": {
        "label": "戰術方案",
        "failures": {
            "被包圍": {"variables": ["encirclement"]},
            "補給斷": {"variables": ["supply_delay", "resource_shortage"]},
            "情報錯": {"variables": ["intelligence_error", "sensor_failure"]},
            "隊形崩": {"variables": ["formation_collapse"]},
        },
    },
    "city_takeover": {
        "label": "城市接管",
        "failures": {
            "治安反彈": {"variables": ["public_order_collapse", "civilian_pressure"]},
            "糧食不足": {"variables": ["resource_shortage", "supply_delay"]},
            "行政癱瘓": {"variables": ["administration_collapse"]},
            "民心下滑": {"variables": ["public_sentiment_decline"]},
        },
    },
    "equipment": {
        "label": "裝備方案",
        "failures": {
            "過熱": {
                "variables": ["equipment_overheat"],
                "checks": ["virtual_test.physical.heat"],
            },
            "續航不足": {
                "variables": ["endurance_shortfall"],
                "checks": ["virtual_test.physical.energy"],
            },
            "跌倒": {"checks": ["virtual_test.physical.stability"]},
            "維修時間過長": {"checks": ["virtual_test.engineering.maintenance"]},
        },
    },
    "hades_aerogrid": {
        "label": "HADES / AEROGRID",
        "failures": {
            "漏檢": {"variables": ["sensor_failure"]},
            "誤判": {"variables": ["misidentification"]},
            "反應太慢": {"variables": ["reaction_delay"]},
            "目標太多": {"variables": ["target_saturation"]},
        },
    },
    "skyfox": {
        "label": "SKYFOX",
        "failures": {
            "失聯": {"variables": ["communication_failure"]},
            "撞機": {"variables": ["collision"]},
            "能源耗盡": {"variables": ["energy_depletion"]},
            "路徑阻塞": {"variables": ["path_blocked"]},
        },
    },
    "startx_plan": {
        "label": "STARTX 方案",
        "failures": {
            "長期資源壓力爆炸": {"variables": ["resource_shortage", "supply_delay"]},
            "戰略節奏延誤": {"variables": ["tempo_delay"]},
        },
    },
    "tac_angel_action": {
        "label": "TAC ANGEL 行動",
        "failures": {
            "局部打贏但戰略上浪費成本": {
                "checks": [
                    "anti_gaming.sacrifice_strategic_value_for_short_term_tactical_value"
                ]
            },
        },
    },
}


def variables_for(plan_class: str) -> list[str]:
    """Every failure variable that tests a class of plan, in table order."""
    found: dict[str, None] = {}
    for way in FAILURE_TAXONOMY[plan_class]["failures"].values():
        for name in way.get("variables", []):
            found[name] = None
    return list(found)
