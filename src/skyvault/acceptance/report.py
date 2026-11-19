"""acceptance.md: SKYVAULT 2.0's acceptance, for a person to read (pure)."""

import json
from typing import Any

from ..boundary import MAY, MAY_NOT, ROLE

FOUNDING = (
    ("formal_spec_0", "Formal Spec §0 — 從正式文件抽出的硬性要求"),
    ("contracts", "Formal Spec §2 – §18 — 契約逐欄"),
    ("phases", "Formal Spec §21 — 長期版本框架的通過標準"),
    ("definition", "SKYVAULT Definition"),
)
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
    "formal_spec_0": "Formal Spec §0",
    "contracts": "contracts §2–§18",
    "phases": "§21 phases",
    "definition": "Definition",
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
    regression = result["regression"]
    rows = {
        **{key: result[key] for key, _ in FOUNDING},
        "acceptance": regression["acceptance"],
        "must_have": regression["must_have"],
        "may": regression["boundary"]["may"],
        "may_not": regression["boundary"]["may_not"],
    }
    counts = result["counts"]
    verdict = "ACCEPTED" if result["passed"] else "NOT ACCEPTED"
    lines = [
        "# SKYVAULT 2.0 acceptance",
        "",
        f"**{verdict}** against the Formal Spec and the SKYVAULT Definition — "
        + ", ".join(
            f"{counts[k]['passed']}/{counts[k]['of']} {SHORT[k]}" for k, _ in FOUNDING
        ),
        "",
        "Regression (Phase 20): "
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
        "Every line below ran now, on one SKYVAULT service: the regression first, "
        "then the founding documents.",
        "",
    ]
    for key, title in FOUNDING:
        lines += [
            f"## {title}",
            "",
            "| | source | check | evidence |",
            "|---|---|---|---|",
        ]
        for row in rows[key]:
            mark = "✅" if row["passed"] else "❌"
            lines.append(
                f"| {mark} | {row['source']} | {row['title']} | "
                f"{_evidence(row['evidence'])} |"
            )
        lines.append("")
    lines += ["# Regression — the Phase 20 checks", ""]
    for key, title in SECTIONS:
        lines += [f"## {title}", "", "| | check | evidence |", "|---|---|---|"]
        for row in rows[key]:
            mark = "✅" if row["passed"] else "❌"
            lines.append(f"| {mark} | {row['title']} | {_evidence(row['evidence'])} |")
        lines.append("")
    return "\n".join(lines)
