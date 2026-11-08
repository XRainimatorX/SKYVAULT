"""acceptance.md: Full SKYVAULT v2.0's acceptance, for a person to read (pure)."""

import json
from typing import Any

from ..boundary import MAY, MAY_NOT, ROLE

SECTIONS = (
    ("acceptance", "Final acceptance criteria"),
    ("must_have", "What Full v2.0 must have"),
    ("may", "Final Authority Boundary — SKYVAULT may"),
    (
        "may_not",
        "Final Authority Boundary — SKYVAULT may not (each one tried and refused)",
    ),
)

SHORT = {
    "acceptance": "acceptance criteria",
    "must_have": "must-haves",
    "may": "things SKYVAULT may do",
    "may_not": "things it may not do (refused)",
}


def _evidence(evidence: dict[str, Any]) -> str:
    parts = []
    for key, value in evidence.items():
        shown = (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )
        parts.append(f"{key}: {shown}")
    return "; ".join(parts).replace("|", "/")


def acceptance_report(result: dict[str, Any]) -> str:
    rows = {
        "acceptance": result["acceptance"],
        "must_have": result["must_have"],
        "may": result["boundary"]["may"],
        "may_not": result["boundary"]["may_not"],
    }
    counts = result["counts"]
    verdict = "ACCEPTED" if result["passed"] else "NOT ACCEPTED"
    lines = [
        "# SKYVAULT v2.0 acceptance",
        "",
        f"**{verdict}** — "
        + ", ".join(
            f"{counts[k]['passed']}/{counts[k]['of']} {SHORT[k]}" for k, _ in SECTIONS
        ),
        "",
        f"SKYVAULT's role: {ROLE.replace('_', ' ')}. It may "
        + ", ".join(MAY)
        + "; it may not "
        + ", ".join(MAY_NOT)
        + ".",
        "",
        "Every line below ran now, on one SKYVAULT service, in this order.",
        "",
    ]
    for key, title in SECTIONS:
        lines += [f"## {title}", "", "| | check | evidence |", "|---|---|---|"]
        for row in rows[key]:
            mark = "✅" if row["passed"] else "❌"
            lines.append(f"| {mark} | {row['title']} | {_evidence(row['evidence'])} |")
        lines.append("")
    return "\n".join(lines)
