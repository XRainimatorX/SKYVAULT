"""The constraint solver: how far each parameter must move for its limit to hold.

Important:
Pure. For every check that is impossible (or a warning), the parameter
that check rests on is solved with scipy.optimize.brentq until the margin
is exactly 0 (impossible → just possible) or warning_margin (a warning →
clear of it). Putting the required value back into the profile makes that
check land on its target: the trigger is a number to design to, not advice.

mass_limit solves the other way round: the heaviest the equipment can be
(with everything else as given) before a mass-bound check — joint_load or
ground_pressure — fails.
"""

import math
from typing import Any

from scipy.optimize import brentq

from .physics import margins, physical_possibility
from .profile import physical, with_param

# the parameter each check is solved on: raise it to gain margin
LEVERS = {
    "stability": "base_width",
    "joint_load": "joint_load",
    "ground_pressure": "footprint",
    "energy": "energy_capacity",
    "heat": "cooling_capacity",
}
MASS_BOUND = ("joint_load", "ground_pressure")
GROUP = "physical_parameters"


def solve(
    profile: dict[str, Any],
    rules: dict[str, Any],
    check: str,
    parameter: str,
    target: float,
) -> float | None:
    """
    The value of parameter at which check's margin equals target, searched
    upwards from the current value; None when no value up to a thousand
    times it gets there (or the check cannot be judged).
    """
    current = physical(profile, parameter)
    if current is None:
        return None

    def gap(value: float) -> float:
        margin = margins(with_param(profile, GROUP, parameter, value), rules)[check]
        return -1.0 if margin is None else float(margin) - target

    low = max(current, 1e-9)
    if gap(low) >= 0:
        return round(low, 6)
    high = low * 1000
    if gap(high) < 0:
        return None
    # rounded up, so the value given is never just short of the target
    return math.ceil(float(brentq(gap, low, high, xtol=1e-9)) * 1e4) / 1e4


def mass_limit(profile: dict[str, Any], rules: dict[str, Any]) -> float | None:
    """The largest mass at which every mass-bound check still holds, or None."""
    mass = physical(profile, "mass")
    if mass is None:
        return None

    def worst(value: float) -> float:
        found = margins(with_param(profile, GROUP, "mass", value), rules)
        known = [float(m) for c in MASS_BOUND if (m := found[c]) is not None]
        return min(known) if known else 1.0

    tiny, huge = 1e-6, max(mass, 1.0) * 1000
    if worst(huge) >= 0:
        return None  # nothing mass-bound ever fails
    if worst(tiny) < 0:
        return 0.0
    # rounded down, so the limit given never just breaks a check
    return math.floor(float(brentq(worst, tiny, huge, xtol=1e-6)) * 1e3) / 1e3


def redesign_triggers(profile: dict[str, Any], rules: dict[str, Any]) -> list[dict]:
    """
    One trigger per impossible or warning check that has a lever:
    {constraint, status, parameter, current, required, change, target_margin};
    change is the required relative increase (0.2 = 20 % more).
    """
    triggers = []
    for item in physical_possibility(profile, rules)["checks"]:
        check, status = item["check"], item["status"]
        if status not in ("impossible", "warning") or check not in LEVERS:
            continue
        parameter = LEVERS[check]
        target = 0.0 if status == "impossible" else float(rules["warning_margin"])
        required = solve(profile, rules, check, parameter, target)
        current = physical(profile, parameter)
        triggers.append(
            {
                "constraint": check,
                "status": status,
                "parameter": parameter,
                "current": current,
                "required": required,
                "change": (
                    None
                    if required is None or not current
                    else round(required / current - 1, 4)
                ),
                "target_margin": target,
            }
        )
    limit = mass_limit(profile, rules)
    mass = physical(profile, "mass")
    if limit is not None and mass is not None and limit < mass:
        triggers.append(
            {
                "constraint": "mass_limit",
                "status": "impossible",
                "parameter": "mass",
                "current": mass,
                "required": limit,
                "change": round(limit / mass - 1, 4),
                "target_margin": 0.0,
            }
        )
    return triggers
