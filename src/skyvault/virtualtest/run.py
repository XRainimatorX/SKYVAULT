"""virtual_test = one profile through the three tests, the stress and the judgement.

Important:
The equipment_test_result of Formal Spec section 18, validated against its
contract. tactical=False skips the scenario runs (the result's tactical
score is then None: not tested, never "useful"); surrogate=True also fits
the surrogate model and predicts what the redesign triggers would do to the
tactical value.
"""

from typing import Any

from ..contracts import validate_equipment_profile, validate_equipment_test_result
from .engineering import engineering_feasibility
from .external import ExternalSimulator, external_simulation
from .physics import physical_possibility
from .profile import load_rules, with_param
from .solver import redesign_triggers
from .stress import explore_equipment
from .surrogate import fit, predict
from .tactical import tactical_usefulness


def _not_tested(profile: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    from .tactical import logistics_burden

    return {
        "score": None,
        "useful_contexts": [],
        "weak_contexts": [],
        "logistics_burden": logistics_burden(profile, rules),
        "contexts": [],
        "unit": {},
    }


def virtual_test(
    profile: dict[str, Any],
    rules: dict[str, Any] | None = None,
    scenarios: list[str] | None = None,
    seeds: list[int] | None = None,
    tactical: bool = True,
    surrogate: bool = False,
    simulator: ExternalSimulator | None = None,
    replace: str | None = None,
) -> dict[str, Any]:
    """The equipment_test_result for profile (replace: the unit it stands in for)."""
    profile = validate_equipment_profile(profile)
    rules = rules or load_rules()
    physics = physical_possibility(profile, rules)
    engineering = engineering_feasibility(profile, rules)
    usefulness = (
        tactical_usefulness(profile, rules, scenarios, seeds, replace)
        if tactical
        else _not_tested(profile, rules)
    )
    explored = explore_equipment(profile, rules)
    triggers = redesign_triggers(profile, rules)
    external = external_simulation(profile, rules, simulator)
    from .judgement import final_judgement

    result: dict[str, Any] = {
        "equipment_id": profile["equipment_id"],
        "category": profile["category"],
        "physical_possibility": physics,
        "engineering_feasibility": engineering,
        "tactical_usefulness": usefulness,
        "failure_exploration": {
            "failure_points": explored["failure_points"],
            "collapse_sequence": explored["collapse_sequence"],
            "redesign_triggers": triggers,
        },
        "require_external_simulation": external,
        "final_judgement": final_judgement(
            physics, engineering, usefulness, external, triggers, rules
        ),
    }
    if surrogate:
        names = list(scenarios or rules["tactical"]["scenarios"])[:1]
        quick = list(seeds or rules["tactical"]["seeds"])[:2]

        def measure(variant: dict[str, Any]) -> float:
            found = tactical_usefulness(variant, rules, names, quick)
            applicable = [c for c in found["contexts"] if c["applicable"]]
            if not applicable:
                return 0.0
            return float(applicable[0]["versus_baseline"]["mean_score"])

        model = fit(profile, measure)
        redesigned = profile
        for trigger in triggers:
            if trigger["required"] is not None:
                redesigned = with_param(
                    redesigned,
                    "physical_parameters",
                    trigger["parameter"],
                    trigger["required"],
                )
        result["surrogate"] = {
            "model": model,
            "scenario": names[0] if names else None,
            "redesign_prediction": predict(model, redesigned),
        }
    return validate_equipment_test_result(result)
