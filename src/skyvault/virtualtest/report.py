"""virtual_test_report.md: what the virtual test found, for a person to read (pure)."""

from typing import Any

PURPOSE = {"impossible": "to make it possible", "warning": "to clear the warning"}


def _score(value: Any) -> str:
    # three places: 0.4961 must not read as the 0.50 it falls short of
    return "—" if value is None else f"{float(value):.3f}"


def _list(items: list[str], empty: str = "none") -> str:
    return "; ".join(items) if items else empty


def virtual_test_report(results: list[dict[str, Any]]) -> str:
    """One summary table, then each profile's three tests, failures and judgement."""
    lines = [
        "# Virtual test report",
        "",
        "Physics-lite screening before a prototype: is it roughly possible, is it",
        "worth building, does it help in a mission, and where does it fail. It does",
        "not replace CAD / CAE / FEA; it says when they are needed.",
        "",
        "| equipment | category | physical | engineering | tactical | judgement |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['equipment_id']} | {r['category']} | "
            f"{_score(r['physical_possibility']['score'])} | "
            f"{_score(r['engineering_feasibility']['score'])} | "
            f"{_score(r['tactical_usefulness']['score'])} | "
            f"{r['final_judgement']['status']} |"
        )
    lines.append("")
    for r in results:
        physics = r["physical_possibility"]
        engineering = r["engineering_feasibility"]
        tactical = r["tactical_usefulness"]
        failures = r["failure_exploration"]
        external = r["require_external_simulation"]
        lines += [
            f"## {r['equipment_id']} ({r['category']})",
            "",
            f"**{r['final_judgement']['status']}** — {r['final_judgement']['reason']}",
            "",
            f"- Impossible: {_list(physics['impossible_flags'])}",
            f"- Warnings: {_list(physics['warnings'])}",
            f"- Engineering bottlenecks: {_list(engineering['bottlenecks'])}",
            f"- Maintenance risks: {_list(engineering['maintenance_risks'])}",
            f"- Useful in: {_list(tactical['useful_contexts'])}; weak in: "
            f"{_list(tactical['weak_contexts'])}; logistics burden "
            f"{tactical['logistics_burden'] or 'not judged'}",
        ]
        broken = [
            f"{p['condition']} at {p['level']} ({', '.join(p['breaks'])})"
            for p in failures["failure_points"]
            if p["level"] is not None
        ]
        held = [
            p["condition"] for p in failures["failure_points"] if p["level"] is None
        ]
        lines.append(
            f"- Newly fails under: {_list(broken)}; nothing new fails under: "
            f"{_list(held)} (what already fails is listed as impossible above)"
        )
        sequence = [
            f"{step['level']}: {', '.join(step['fails'])}"
            for step in failures["collapse_sequence"]
        ]
        lines.append(f"- Collapse sequence: {_list(sequence, 'nothing fails')}")
        triggers = [
            f"{t['parameter']} {t['current']} → {t['required']} ({t['constraint']}, "
            f"{PURPOSE[t['status']]})"
            for t in failures["redesign_triggers"]
        ]
        lines.append(f"- Redesign triggers: {_list(triggers)}")
        lines.append(
            "- External simulation: "
            + (
                "required — " + _list(external["reasons"])
                if external["required"]
                else "not needed"
            )
        )
        lines.append("")
    return "\n".join(lines)
