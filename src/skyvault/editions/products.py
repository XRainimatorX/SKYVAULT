"""The six commercial products: each a flow over the core, with what it is worth.

Important:
A product owns no simulation, evaluation or report code of its own: every
number comes from a core function run here (domain packs, batch, policy
registry, evaluation, virtual test, briefing, failure exploration). What a
product adds is the question it answers, the key figures (kpis) a
customer reads, and a conclusion in plain words.

"Shows its value" means: the kpis are not empty, they come from a real run
made now, and in the commercial edition no internal name is left in them.

A product may be given the customer's own scenario (scenario=...) in place
of its reference one; feedback.py carries such a scenario back to the core.
"""

import copy
import json
from pathlib import Path
from typing import Any

from ..batch.run import run_batch
from ..domains.city.pack import CITY
from ..domains.city.report import cascade
from ..engine import SkyVaultEngine
from ..failure import build_failure_map, explore_failures
from ..report import build_briefing, render_markdown
from ..scenario_loader import default_evaluation_profile, load_scenario
from ..virtualtest.profile import load_profile
from ..virtualtest.run import virtual_test
from .manifest import EDITIONS, allows
from .redact import redact

ROOT = Path(__file__).resolve().parents[3]
SCENARIOS = ROOT / "data" / "scenarios"
BATCHES = ROOT / "data" / "batches"


def catalogue() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = json.loads(
        (EDITIONS / "products.json").read_text(encoding="utf-8")
    )["products"]
    return found


def _scenario(name: str) -> dict[str, Any]:
    return load_scenario(SCENARIOS / name / "v0.1.json")


def _run(scenario: dict[str, Any], **runtime: Any) -> dict[str, Any]:
    scenario = copy.deepcopy(scenario)
    scenario["runtime"].update(runtime)
    return SkyVaultEngine(scenario).run()


def crisis_planning(scenario: dict[str, Any] | None) -> dict[str, Any]:
    scenario = scenario or _scenario("city_blackout_001")
    package = _run(scenario)
    governance = CITY.governance_outcome(package, scenario)
    chain = cascade(package)
    kpis = {
        "outcome": package["evaluation_result"]["winner_or_result"],
        "governance_score": governance["score"],
        "governance_score_at_start": governance["start"],
        "cascade_depth": chain["cascade_depth"],
        "most_districts_dark": chain["most_dark"],
    }
    held = kpis["outcome"] in ("order_restored", "order_held")
    conclusion = (
        f"The outage spread {chain['cascade_depth']} step(s) and left at most "
        f"{chain['most_dark']} district(s) dark; governance stability went from "
        f"{governance['start']:.2f} to {governance['score']:.2f} and public "
        f"order was {'held' if held else 'not restored'}."
    )
    return {"kpis": kpis, "conclusion": conclusion, "outputs": {"cascade": chain}}


def urban_resilience(scenario: dict[str, Any] | None, repeats: int) -> dict[str, Any]:
    spec = json.loads((BATCHES / "city_supply_delay.json").read_text("utf-8"))
    spec["run_policy"]["repeat_count"] = repeats
    result = run_batch(spec)["batch_result"]
    rates = {
        v["variant_id"].rsplit("=", 1)[1]: v["win_rate"] for v in result["variants"]
    }
    holding = [delay for delay, rate in rates.items() if rate >= 0.5]
    kpis = {
        "order_restored_rate_by_delay": rates,
        "longest_delay_order_holds": max(holding, key=float) if holding else None,
        "runs": len(result["runs"]),
    }
    conclusion = (
        f"Order is restored in at least half the runs up to a supply delay of ×"
        f"{kpis['longest_delay_order_holds']}; beyond it, in fewer than half."
        if holding
        else "Order is not restored at any supply delay tried."
    )
    return {"kpis": kpis, "conclusion": conclusion, "outputs": {}}


AGENTS = {"baseline": None, "rule_based": "rule_based", "scripted": "scripted"}


def ai_scenario_testing(scenario: dict[str, Any] | None) -> dict[str, Any]:
    scenario = scenario or _scenario("military_squad_001")
    agents = {}
    for label, name in AGENTS.items():
        runtime = {} if name is None else {"policy": {"name": name}}
        verdict = _run(scenario, **runtime)["evaluation_result"]
        agents[label] = {
            "score": verdict["overall_score"],
            "result": verdict["winner_or_result"],
            "gaming_detected": bool(verdict["anti_gaming"].get("gaming_detected")),
        }
    honest = {k: v for k, v in agents.items() if not v["gaming_detected"]}
    top = max(agents, key=lambda k: (agents[k]["score"], k))
    best = max(honest, key=lambda k: (honest[k]["score"], k)) if honest else None
    kpis = {
        "agents": agents,
        "highest_score": top,
        "best_honest_agent": best,
        "flagged_for_gaming": sorted(
            k for k, v in agents.items() if v["gaming_detected"]
        ),
    }
    if top != best:
        conclusion = (
            f"{top} scored highest ({agents[top]['score']:.3f}) but its score is "
            f"flagged as gamed; the best honest agent is {best}."
        )
    else:
        conclusion = f"{top} scored highest and honestly ({agents[top]['score']:.3f})."
    return {"kpis": kpis, "conclusion": conclusion, "outputs": {}}


SCREENED = ("exo_test_001", "pax_test_001", "msx_test_001")


def equipment_screening(scenario: dict[str, Any] | None) -> dict[str, Any]:
    results = {
        name: virtual_test(load_profile(name), tactical=False) for name in SCREENED
    }
    kpis = {
        r["equipment_id"]: {
            "judgement": r["final_judgement"]["status"],
            "physical": r["physical_possibility"]["score"],
            "engineering": r["engineering_feasibility"]["score"],
            "redesign_triggers": len(r["failure_exploration"]["redesign_triggers"]),
        }
        for r in results.values()
    }
    verdicts = ", ".join(f"{k} {v['judgement']}" for k, v in kpis.items())
    return {
        "kpis": kpis,
        "conclusion": f"Screened before any prototype: {verdicts}.",
        "outputs": {r["equipment_id"]: r["final_judgement"] for r in results.values()},
    }


def training_aar(scenario: dict[str, Any] | None) -> dict[str, Any]:
    scenario = scenario or _scenario("military_squad_001")
    package = _run(scenario)
    events = package["event_memory"]
    attacks = [e for e in events if e["event_type"] == "ATTACK"]
    lost = [e for e in events if e["event_type"] == "ENTITY_DESTROYED"]
    kpis = {
        "outcome": package["evaluation_result"]["winner_or_result"],
        "ticks": package["final_world_state"]["tick"],
        "events": len(events),
        "first_contact_tick": attacks[0]["time"] if attacks else None,
        "units_lost": len(lost),
    }
    briefing = render_markdown(build_briefing({"result_package": package}))
    conclusion = (
        f"{kpis['ticks']} ticks, {len(events)} recorded events; first shots at tick "
        f"{kpis['first_contact_tick']}, {kpis['units_lost']} unit(s) lost — "
        f"{kpis['outcome']}."
    )
    return {"kpis": kpis, "conclusion": conclusion, "outputs": {"briefing": briefing}}


def risk_studio(scenario: dict[str, Any] | None, repeats: int) -> dict[str, Any]:
    scenario = scenario or _scenario("airspace_defence_001")
    config = copy.deepcopy(scenario["failure_exploration"])
    config["run_policy"]["repeat_count"] = repeats
    failure_map = build_failure_map(
        explore_failures(scenario, default_evaluation_profile(scenario), config)
    )
    breaking = {
        v["variable"]: v.get("breaking_level") for v in failure_map["variables"]
    }
    kpis = {
        "baseline_survival": failure_map["baseline"]["survival_rate"],
        "breaking_level": breaking,
        "crushing_variable": failure_map["crushing_variable"],
    }
    conclusion = (
        f"The plan survives {failure_map['baseline']['survival_rate']:.0%} of runs "
        f"unstressed; {failure_map['crushing_variable']} crushes it first."
    )
    return {"kpis": kpis, "conclusion": conclusion, "outputs": {}}


def run_product(
    product_id: str,
    edition: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    repeats: int = 3,
) -> dict[str, Any]:
    """
    {product, title, question, kpis, conclusion, outputs}, redacted for the
    edition. PermissionError for a product the edition does not offer.
    """
    if not allows(edition, "product", product_id):
        raise PermissionError(
            f"the {edition['edition_id']} edition does not offer {product_id!r}"
        )
    flows = {
        "crisis_planning": lambda: crisis_planning(scenario),
        "urban_resilience": lambda: urban_resilience(scenario, repeats),
        "ai_scenario_testing": lambda: ai_scenario_testing(scenario),
        "equipment_screening": lambda: equipment_screening(scenario),
        "training_aar": lambda: training_aar(scenario),
        "risk_studio": lambda: risk_studio(scenario, repeats),
    }
    entry = catalogue()[product_id]
    result = {
        "product": product_id,
        "title": entry["title"],
        "question": entry["question"],
        **flows[product_id](),
    }
    return redact(result, edition)


def product_report(results: list[dict[str, Any]], edition: dict[str, Any]) -> str:
    """products.md: each product's question, key figures and conclusion."""
    lines = [f"# {edition['title']} — products", ""]
    for r in results:
        lines += [f"## {r['title']}", "", f"*{r['question']}*", "", r["conclusion"], ""]
        for key, value in r["kpis"].items():
            shown = json.dumps(value, ensure_ascii=False, sort_keys=True)
            lines.append(f"- {key}: {shown}")
        lines.append("")
    return redact("\n".join(lines), edition)
