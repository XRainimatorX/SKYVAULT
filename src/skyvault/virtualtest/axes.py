"""Equipment axes = what a scenario's equipment profiles add to its evaluation.

Important:
Formal Spec 8.2 begins with physical possibility and engineering
feasibility. A scenario that brings equipment into the world
(participants.equipment_profiles) is judged on both: each profile is
screened as the virtual test screens it, and the scenario scores the mean,
naming every profile and its score.
"""

from typing import Any

from .engineering import engineering_feasibility
from .physics import physical_possibility
from .profile import load_profile, load_rules


def equipment_axes(names: list[str]) -> dict[str, tuple[float, str]]:
    """{axis: (score, explanation)} for the named equipment profiles."""
    rules = load_rules()
    physical: list[tuple[str, float]] = []
    engineering: list[tuple[str, float]] = []
    for name in names:
        profile: dict[str, Any] = load_profile(name)
        physical.append((name, float(physical_possibility(profile, rules)["score"])))
        engineering.append(
            (name, float(engineering_feasibility(profile, rules)["score"]))
        )

    def axis(scored: list[tuple[str, float]]) -> tuple[float, str]:
        mean = round(sum(score for _, score in scored) / len(scored), 4)
        listed = ", ".join(f"{name} {score:.2f}" for name, score in scored)
        return mean, f"mean of the equipment screened: {listed}"

    return {
        "physical_possibility": axis(physical),
        "engineering_feasibility": axis(engineering),
    }
