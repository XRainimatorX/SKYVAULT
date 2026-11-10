"""Trade-off report = what the plan gained, and what it paid for it.

Important:
Both functions are pure. build_tradeoff_report() returns plain data that goes
into the result package; render_tradeoff_report() turns it into Markdown for
the runner to write.
"""

from typing import Any

# Axes that pull against each other: (what is gained, what it tends to cost)
TRADEOFFS = (
    ("tactical_value", "strategic_value"),
    ("mission_success", "resource_cost"),
    ("time_cost", "risk_growth"),
    ("mission_success", "stability_impact"),
)

STRONG = 0.6
WEAK = 0.4


def _assess(gain: dict[str, Any], cost: dict[str, Any], names: tuple[str, str]) -> str:
    if not (gain["applicable"] and cost["applicable"]):
        return "not assessable: an axis had no data"
    a, b = gain["score"], cost["score"]
    if a >= STRONG and b >= STRONG:
        return "both strong"
    if a < WEAK and b < WEAK:
        return "both weak"
    if a >= STRONG and b < WEAK:
        return f"{names[0]} bought at the expense of {names[1]}"
    if b >= STRONG and a < WEAK:
        return f"{names[1]} kept at the expense of {names[0]}"
    return "balanced"


def build_tradeoff_report(
    score_breakdown: dict[str, dict[str, Any]],
    anti_gaming_report: dict[str, Any],
    judgement: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    The trade-off report as data.

    judgement holds scenario_id, status, confidence and overall_score.
    strongest and weakest rank the weighted axes that had data.
    """
    tradeoffs = []
    for gain_name, cost_name in TRADEOFFS:
        gain, cost = score_breakdown[gain_name], score_breakdown[cost_name]
        tradeoffs.append(
            {
                "gain": gain_name,
                "gain_score": gain["score"],
                "cost": cost_name,
                "cost_score": cost["score"],
                "assessment": _assess(gain, cost, (gain_name, cost_name)),
            }
        )

    ranked = sorted(
        (
            (name, entry["score"])
            for name, entry in score_breakdown.items()
            if entry["applicable"] and entry["weight"] > 0
        ),
        key=lambda item: (-item[1], item[0]),
    )

    return {
        "scenario_id": judgement["scenario_id"],
        "profile_id": profile["profile_id"],
        "perspective": profile["perspective"],
        "required": profile["tradeoff_report_required"],
        "judgement": {
            "status": judgement["status"],
            "confidence": judgement["confidence"],
            "overall_score": judgement["overall_score"],
        },
        "tradeoffs": tradeoffs,
        "strongest": [{"metric": n, "score": s} for n, s in ranked[:3]],
        "weakest": [
            {"metric": n, "score": s}
            for n, s in sorted(ranked, key=lambda item: (item[1], item[0]))[:3]
        ],
        "anti_gaming": {
            "gaming_detected": anti_gaming_report["gaming_detected"],
            "flagged_behaviors": list(anti_gaming_report["flagged_behaviors"]),
            "triggered_behaviors": list(anti_gaming_report["triggered_behaviors"]),
        },
    }


def render_tradeoff_report(report: dict[str, Any]) -> str:
    """The trade-off report as Markdown."""
    judgement = report["judgement"]
    lines = [
        f"# Trade-off report — {report['scenario_id']}",
        "",
        f"- Profile: `{report['profile_id']}`",
        f"- Perspective: {report['perspective']}",
        f"- Verdict: **{judgement['status']}** "
        f"(overall {judgement['overall_score']:.2f}, "
        f"confidence {judgement['confidence']:.2f})",
        "",
        "## Trade-offs",
        "",
        "| Gain | Score | Cost | Score | Assessment |",
        "|---|---|---|---|---|",
    ]
    for item in report["tradeoffs"]:
        lines.append(
            f"| {item['gain']} | {item['gain_score']:.2f} "
            f"| {item['cost']} | {item['cost_score']:.2f} | {item['assessment']} |"
        )

    lines += ["", "## Strongest axes", ""]
    lines += [f"- {e['metric']}: {e['score']:.2f}" for e in report["strongest"]]
    lines += ["", "## Weakest axes", ""]
    lines += [f"- {e['metric']}: {e['score']:.2f}" for e in report["weakest"]]

    gaming = report["anti_gaming"]
    lines += ["", "## Anti-gaming", ""]
    if gaming["gaming_detected"]:
        lines.append("Gaming detected: " + ", ".join(gaming["flagged_behaviors"]) + ".")
    else:
        lines.append("No forbidden optimisation behaviour detected.")
    allowed = [
        behavior
        for behavior in gaming["triggered_behaviors"]
        if behavior not in gaming["flagged_behaviors"]
    ]
    if allowed:
        lines.append(
            "Triggered but allowed by this profile: " + ", ".join(allowed) + "."
        )

    return "\n".join(lines) + "\n"
