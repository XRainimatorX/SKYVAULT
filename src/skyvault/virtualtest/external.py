"""When physics-lite is not enough: the external simulation flag and its adapter.

Important:
SKYVAULT does not replace CAD / CAE / FEA (Formal Spec section 19 D); it
says when they are needed. require_external_simulation is raised for:

- a physical margin inside the uncertainty band (|margin| < band): the
  screening rules cannot tell pass from fail that close to the line
- a mass for its height outside the category's range (scale): the rules
  were not made for this design
- a category the rules have no envelope for
- a check the profile does not give the inputs for

The adapter is a protocol (simulate(profile, questions)); the stand-in
returns "not_run" with the questions it was asked. It never invents a
result. FMI / FMU co-simulation is a later adapter behind the same call.
"""

from typing import Any, Protocol

from .physics import margins
from .profile import category_rules


class ExternalSimulator(Protocol):
    name: str

    def simulate(
        self, profile: dict[str, Any], questions: list[str]
    ) -> dict[str, Any]: ...


class StandInSimulator:
    """No simulator attached: the questions come back unanswered."""

    name = "stand_in"

    def simulate(self, profile: dict[str, Any], questions: list[str]) -> dict:
        return {
            "simulator": self.name,
            "status": "not_run",
            "questions": list(questions),
            "note": "no external simulation adapter is attached (FMI / FMU later)",
        }


def external_simulation(
    profile: dict[str, Any],
    rules: dict[str, Any],
    simulator: ExternalSimulator | None = None,
) -> dict[str, Any]:
    """{required, reasons, adapter}: the adapter is asked only when required."""
    band = float(rules["uncertainty_band"])
    reasons = []
    for check, margin in margins(profile, rules).items():
        if margin is None:
            reasons.append(f"{check}: not enough parameters to judge")
        elif check == "scale" and margin < 0:
            reasons.append("scale: outside the range the category's rules cover")
        elif abs(margin) < band:
            reasons.append(f"{check}: margin {margin:+.3f} is within ±{band}")
    if category_rules(profile, rules) is None:
        reasons.insert(0, f"category {profile['category']!r} is unknown to the rules")
    adapter = (
        (simulator or StandInSimulator()).simulate(profile, reasons) if reasons else {}
    )
    return {"required": bool(reasons), "reasons": reasons, "adapter": adapter}
