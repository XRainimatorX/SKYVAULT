"""engineering_feasibility = worth building? materials, upkeep, parts, supply, repair.

Important:
Pure. Five components, each 0–1, weighted by rules.engineering.weights:

material      material_complexity: low 1.0 … exotic 0.25
maintenance   1 / (1 + maintenance_time / endurance): the hours of upkeep
              each hour of operation costs (1 h per hour → 0.5)
parts         part_replacement_difficulty: easy 1.0 … hard 0.4
supply        1 − supply_chain_risk
repair        repair_environment_required: field 1.0 … factory 0.3

"Worth investing" is a score of at least rules.engineering.worth_investing.
A component the profile does not give is left out of the mean and listed
as a risk, never counted as perfect.
"""

from typing import Any

from .profile import param, physical


def maintenance_ratio(profile: dict[str, Any]) -> float | None:
    """Hours of maintenance per hour of operation, or None."""
    hours = param(profile, "engineering_parameters", "maintenance_time")
    endurance = physical(profile, "endurance")
    if hours is None or not endurance:
        return None
    return round(float(hours) / endurance, 6)


def engineering_feasibility(profile: dict[str, Any], rules: dict[str, Any]) -> dict:
    """{score, bottlenecks, maintenance_risks, components}."""
    table = rules["engineering"]
    eng = profile.get("engineering_parameters") or {}
    ratio = maintenance_ratio(profile)
    risk = eng.get("supply_chain_risk")
    components: dict[str, float | None] = {
        "material": table["material"].get(eng.get("material_complexity")),
        "maintenance": None if ratio is None else round(1 / (1 + ratio), 4),
        "parts": table["parts"].get(eng.get("part_replacement_difficulty")),
        "supply": None if risk is None else round(1 - float(risk), 4),
        "repair": table["repair"].get(eng.get("repair_environment_required")),
    }
    weights = table["weights"]
    known = {k: v for k, v in components.items() if v is not None}
    total = sum(float(weights[k]) for k in known)
    score = (
        round(sum(float(weights[k]) * float(v) for k, v in known.items()) / total, 4)
        if total
        else 0.0
    )
    bottlenecks = []
    if eng.get("material_complexity") == "exotic":
        bottlenecks.append("exotic materials")
    if ratio is not None and ratio > 1:
        bottlenecks.append(
            f"more maintenance than operation ({ratio:.1f} h per hour run)"
        )
    if eng.get("repair_environment_required") == "factory":
        bottlenecks.append("repairs need a factory")
    if risk is not None and float(risk) >= float(table["supply_risk_high"]):
        bottlenecks.append(f"supply chain risk {float(risk):.0%}")
    maintenance_risks = []
    if ratio is not None and ratio > 0.5:
        maintenance_risks.append(f"{ratio:.1f} h of maintenance per hour of operation")
    if eng.get("part_replacement_difficulty") == "hard":
        maintenance_risks.append("parts are hard to replace")
    if eng.get("repair_environment_required") in ("depot", "factory"):
        maintenance_risks.append(
            f"cannot be repaired in the field ({eng['repair_environment_required']})"
        )
    maintenance_risks += [
        f"{name}: not given" for name, value in components.items() if value is None
    ]
    return {
        "score": score,
        "bottlenecks": bottlenecks,
        "maintenance_risks": maintenance_risks,
        "components": components,
    }
