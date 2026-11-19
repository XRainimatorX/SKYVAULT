"""Metrics = the evaluation axes, each computed from what a run recorded.

Important:
Everything here reads plain dicts (initial world state, event memory, final
world state) and imports nothing from the rest of the project. A score can
only reflect what event memory holds, never what the engine happened to know.

Every score is in [0, 1] and higher is better. Cost-like axes are inverted:
resource_cost 1.0 means nothing was lost. The raw number behind each score is
kept next to it in the score breakdown.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MetricValue:
    """
    One axis for one run.

    applicable is False when the run holds no data the axis could judge (no
    resources to spend, no losses to recover from). Such an axis scores 0 and
    is left out of the weighted total; it lowers the verdict's confidence.

    in_scope is False when the world does not model what the axis asks
    about at all (physical possibility in a world with no equipment
    profile, governance stability in a world without public order). Such an
    axis is reported as null with its reason and does not lower confidence.
    """

    raw: float
    score: float
    applicable: bool
    explanation: str
    in_scope: bool = True


@dataclass(frozen=True)
class Metric:
    """An evaluation axis: its name, what it measures, and how."""

    name: str
    description: str
    unit: str
    compute: Callable[["EvaluationContext"], MetricValue]


@dataclass
class EvaluationContext:
    """
    One run, indexed once for every metric to read.

    Important:
    perspective is the faction whose plan is being judged. Own entities are
    that faction's; enemies are every other entity that has a faction.
    """

    perspective: str
    initial: dict[str, dict[str, Any]]
    final: dict[str, dict[str, Any]]
    events: list[dict[str, Any]]
    final_tick: int
    max_ticks: int | None
    initial_resources: dict[str, float]
    own: list[str] = field(default_factory=list)
    enemies: list[str] = field(default_factory=list)
    # what the run says about itself (replayable, assumptions declared...),
    # for the axes that judge the run rather than the plan
    facts: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        initial_world_state: dict[str, Any],
        event_memory: list[dict[str, Any]],
        final_world_state: dict[str, Any],
        perspective: str,
        max_ticks: int | None,
    ) -> "EvaluationContext":
        initial = initial_world_state["entities"]
        context = cls(
            perspective=perspective,
            initial=initial,
            final=final_world_state["entities"],
            events=event_memory,
            final_tick=int(final_world_state["tick"]),
            max_ticks=max_ticks,
            initial_resources=dict(initial_world_state.get("resources", {})),
        )
        for entity_id, entity in initial.items():
            faction = entity.get("faction")
            if faction == perspective:
                context.own.append(entity_id)
            elif faction is not None:
                context.enemies.append(entity_id)
        return context

    # ── entity facts ─────────────────────────────────────────────────────────

    def initial_hp(self, entity_id: str) -> float:
        return float(self.initial[entity_id]["state"].get("hp", 0))

    def final_hp(self, entity_id: str) -> float:
        return float(self.final[entity_id]["state"].get("hp", 0))

    def hp_lost(self, entity_id: str) -> float:
        """hp gone over the run; negative hp counts as zero, never as extra loss."""
        return max(0.0, self.initial_hp(entity_id) - max(self.final_hp(entity_id), 0.0))

    def is_active_at_end(self, entity_id: str) -> bool:
        return bool(self.final[entity_id]["state"].get("status") == "active")

    def destroyed_at_end(self, entity_ids: list[str]) -> list[str]:
        return [
            entity_id
            for entity_id in entity_ids
            if self.final[entity_id]["state"].get("status") == "destroyed"
        ]

    # ── event facts ──────────────────────────────────────────────────────────

    def of_type(self, *event_types: str) -> list[dict[str, Any]]:
        return [event for event in self.events if event["event_type"] in event_types]

    def by_own(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [event for event in events if event["source"]["actor_id"] in self.own]

    def against_own(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [event for event in events if event["target_entity_id"] in self.own]

    def own_turns(self) -> list[dict[str, Any]]:
        """Every turn an own entity took: a selected action or an explicit pass."""
        return self.by_own(self.of_type("ACTION_SELECTED", "NO_ACTION"))

    def risk_events_against_own(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self.against_own(self.events)
            if event["evaluation_relevance"]["affects_risk"]
        ]


def _ratio(part: float, whole: float) -> float:
    return part / whole if whole else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _not_applicable(explanation: str) -> MetricValue:
    return MetricValue(raw=0.0, score=0.0, applicable=False, explanation=explanation)


def out_of_scope(explanation: str) -> MetricValue:
    """An axis the world does not model: null, with the reason."""
    return MetricValue(
        raw=0.0, score=0.0, applicable=False, explanation=explanation, in_scope=False
    )


# ── the axes ──────────────────────────────────────────────────────────


def mission_success(context: EvaluationContext) -> MetricValue:
    if not context.enemies:
        return _not_applicable("no opposing faction to succeed against")
    own_left = [e for e in context.own if context.is_active_at_end(e)]
    enemies_left = [e for e in context.enemies if context.is_active_at_end(e)]
    destroyed = context.destroyed_at_end(context.enemies)
    if not own_left:
        score = 0.0
    elif not enemies_left:
        score = 1.0
    else:
        score = _ratio(len(destroyed), len(context.enemies))
    return MetricValue(
        raw=len(destroyed),
        score=score,
        applicable=True,
        explanation=(
            f"{len(destroyed)} of {len(context.enemies)} opposing entities destroyed; "
            f"{len(own_left)} of {len(context.own)} own entities still active"
        ),
    )


def tactical_usefulness(context: EvaluationContext) -> MetricValue:
    enemy_hp = sum(context.initial_hp(e) for e in context.enemies)
    if enemy_hp <= 0:
        return _not_applicable("opposing entities have no hp to damage")
    damage = sum(
        float(event["data"].get("damage", 0))
        for event in context.by_own(context.of_type("ATTACK"))
    )
    return MetricValue(
        raw=damage,
        score=_clamp(_ratio(damage, enemy_hp)),
        applicable=True,
        explanation=f"{damage:g} damage dealt against {enemy_hp:g} opposing hp",
    )


def strategic_value(context: EvaluationContext) -> MetricValue:
    if not context.own:
        return _not_applicable("the perspective faction has no entities")
    kept = [e for e in context.own if context.is_active_at_end(e)]
    return MetricValue(
        raw=len(kept),
        score=_ratio(len(kept), len(context.own)),
        applicable=True,
        explanation=f"{len(kept)} of {len(context.own)} own entities preserved",
    )


def resource_cost(context: EvaluationContext) -> MetricValue:
    own_hp = sum(context.initial_hp(e) for e in context.own)
    if own_hp <= 0:
        return _not_applicable("own entities have no hp to lose")
    lost = sum(context.hp_lost(e) for e in context.own)
    return MetricValue(
        raw=lost,
        score=_clamp(1 - _ratio(lost, own_hp)),
        applicable=True,
        explanation=f"{lost:g} of {own_hp:g} own hp lost",
    )


def time_cost(context: EvaluationContext) -> MetricValue:
    if not context.max_ticks:
        return _not_applicable("the run declares no max_ticks to measure against")
    return MetricValue(
        raw=context.final_tick,
        score=_clamp(1 - _ratio(context.final_tick, context.max_ticks)),
        applicable=True,
        explanation=f"ended at tick {context.final_tick} of {context.max_ticks}",
    )


def risk_growth(context: EvaluationContext) -> MetricValue:
    if not context.own:
        return _not_applicable("the perspective faction has no entities")
    risky = context.risk_events_against_own()
    return MetricValue(
        raw=len(risky),
        score=_clamp(1 - _ratio(len(risky), len(context.own))),
        applicable=True,
        explanation=(
            f"{len(risky)} risk-relevant events hit own entities "
            f"(proxy until a risk model exists)"
        ),
    )


def failure_resistance(context: EvaluationContext) -> MetricValue:
    losses = context.against_own(context.of_type("ENTITY_DESTROYED"))
    if not losses:
        return MetricValue(
            raw=context.final_tick,
            score=1.0,
            applicable=True,
            explanation="no own entity was lost",
        )
    first = min(int(event["time"]) for event in losses)
    return MetricValue(
        raw=first,
        score=_clamp(_ratio(first, context.final_tick)),
        applicable=True,
        explanation=f"first own loss at tick {first} of {context.final_tick}",
    )


def recovery_ability(context: EvaluationContext) -> MetricValue:
    """
    Restored hp over all hp ever lost. hp_lost() is the net loss at the end,
    after repairs, so the gross loss is that plus what was restored.
    """
    lost = sum(context.hp_lost(e) for e in context.own)
    restored = sum(
        float(event["data"].get("hp_after", 0))
        - float(event["data"].get("hp_before", 0))
        for event in context.against_own(context.of_type("REPAIR"))
    )
    if lost <= 0 and restored <= 0:
        return _not_applicable("nothing was lost, so recovery was never tested")
    return MetricValue(
        raw=restored,
        score=_clamp(_ratio(restored, lost + restored)),
        applicable=True,
        explanation=f"{restored:g} hp restored against {lost:g} hp still lost",
    )


def system_robustness(context: EvaluationContext) -> MetricValue:
    selected = context.by_own(context.of_type("ACTION_SELECTED"))
    if not selected:
        return _not_applicable("own entities never selected an action")
    rejected = context.by_own(context.of_type("ACTION_REJECTED"))
    return MetricValue(
        raw=len(rejected),
        score=_clamp(1 - _ratio(len(rejected), len(selected))),
        applicable=True,
        explanation=f"{len(rejected)} of {len(selected)} own actions rejected",
    )


def logistics_burden(context: EvaluationContext) -> MetricValue:
    stock = sum(context.initial_resources.values())
    if stock <= 0:
        return _not_applicable("the world holds no resources to spend")
    spent = -sum(
        min(float(event["data"].get("delta", 0)), 0.0)
        for event in context.by_own(context.of_type("RESOURCE_CHANGED"))
    )
    return MetricValue(
        raw=spent,
        score=_clamp(1 - _ratio(spent, stock)),
        applicable=True,
        explanation=f"{spent:g} of {stock:g} world resource units spent by own actions",
    )


def crisis_resilience(context: EvaluationContext) -> MetricValue:
    """
    How much of the plan's own strength was still standing at its worst
    moment (Formal Spec 8.2: is the plan steadier when crisis strikes?).
    Own hp is followed through every event that recorded it; a domain with
    its own measure of crisis (public order in a city) replaces this.
    """
    start = {e: context.initial_hp(e) for e in context.own}
    total = sum(start.values())
    if total <= 0:
        return _not_applicable("own entities have no strength (hp) to follow")
    current = dict(start)
    worst, worst_tick = total, 0
    for event in context.events:
        target = event["target_entity_id"]
        if target not in current:
            continue
        state = (event.get("after_state") or {}).get("state") or {}
        if "hp" not in state:
            continue
        current[target] = max(float(state["hp"]), 0.0)
        level = sum(current.values())
        if level < worst:
            worst, worst_tick = level, int(event["time"])
    return MetricValue(
        raw=worst,
        score=_clamp(_ratio(worst, total)),
        applicable=True,
        explanation=(
            f"own strength at its lowest {worst:g} of {total:g} hp "
            f"(tick {worst_tick})"
        ),
    )


def physical_possibility(context: EvaluationContext) -> MetricValue:
    return out_of_scope(
        "no equipment profile entered this scenario (participants.equipment_profiles)"
    )


def engineering_feasibility(context: EvaluationContext) -> MetricValue:
    return out_of_scope(
        "no equipment profile entered this scenario (participants.equipment_profiles)"
    )


def governance_stability(context: EvaluationContext) -> MetricValue:
    return out_of_scope("this world models no public order or governance")


def _checklist(context: EvaluationContext, items: dict[str, str]) -> MetricValue:
    if not context.facts:
        return out_of_scope("the run did not describe itself to the evaluation")
    met = [label for key, label in items.items() if context.facts.get(key)]
    missing = [label for key, label in items.items() if not context.facts.get(key)]
    explanation = f"{len(met)} of {len(items)}: " + "; ".join(
        [f"yes {label}" for label in met] + [f"no {label}" for label in missing]
    )
    return MetricValue(
        raw=len(met),
        score=_ratio(len(met), len(items)),
        applicable=True,
        explanation=explanation,
    )


def commercial_demonstrability(context: EvaluationContext) -> MetricValue:
    """
    Could the run be shown to an outside client as it is (Formal Spec 8.2)?
    It can be replayed exactly, something visibly happened, and outside
    systems have slots to enter the world.
    """
    facts = dict(context.facts)
    facts["visible_activity"] = bool(context.own_turns())
    return _checklist(
        EvaluationContext(**{**context.__dict__, "facts": facts}),
        {
            "replayable": "it replays exactly",
            "visible_activity": "own actions to show",
            "actor_slots": "outside systems can enter the world",
        },
    )


def imperial_core_value(context: EvaluationContext) -> MetricValue:
    """
    Does the run keep the long-term architecture (Formal Spec 8.2): its
    assumptions, its data provenance and its failure variables declared,
    and its result replayable?
    """
    return _checklist(
        context,
        {
            "assumptions_declared": "assumptions declared",
            "provenance_declared": "data provenance declared",
            "failure_variables_declared": "failure variables declared",
            "replayable": "it replays exactly",
        },
    )


def stability_impact(context: EvaluationContext) -> MetricValue:
    everyone = list(context.initial)
    if not everyone:
        return _not_applicable("the world has no entities")
    destroyed = context.destroyed_at_end(everyone)
    return MetricValue(
        raw=len(destroyed),
        score=_clamp(1 - _ratio(len(destroyed), len(everyone))),
        applicable=True,
        explanation=(
            f"{len(destroyed)} of {len(everyone)} entities destroyed "
            f"(proxy until a stability model exists)"
        ),
    )


METRIC_REGISTRY: dict[str, Metric] = {
    metric.name: metric
    for metric in (
        Metric(
            "mission_success",
            "Did the perspective faction achieve its aim?",
            "entities",
            mission_success,
        ),
        Metric(
            "tactical_usefulness",
            "Damage dealt against the opposing hp pool",
            "hp",
            tactical_usefulness,
        ),
        Metric(
            "strategic_value",
            "Own force preserved for what comes next",
            "entities",
            strategic_value,
        ),
        Metric("resource_cost", "Own hp lost (1 = nothing lost)", "hp", resource_cost),
        Metric(
            "time_cost",
            "Time used against the limit (1 = no time used)",
            "ticks",
            time_cost,
        ),
        Metric(
            "risk_growth",
            "Risk-relevant events against own entities",
            "events",
            risk_growth,
        ),
        Metric(
            "failure_resistance",
            "How long the plan held before its first loss",
            "ticks",
            failure_resistance,
        ),
        Metric("recovery_ability", "Lost hp that was restored", "hp", recovery_ability),
        Metric(
            "system_robustness",
            "Own actions the world accepted",
            "actions",
            system_robustness,
        ),
        Metric(
            "logistics_burden",
            "World resources spent (1 = nothing spent)",
            "units",
            logistics_burden,
        ),
        Metric(
            "stability_impact",
            "How much of the world survived (1 = nothing destroyed)",
            "entities",
            stability_impact,
        ),
        Metric(
            "physical_possibility",
            "Is the equipment physically roughly possible?",
            "score",
            physical_possibility,
        ),
        Metric(
            "engineering_feasibility",
            "Is the equipment worth engineering?",
            "score",
            engineering_feasibility,
        ),
        Metric(
            "governance_stability",
            "Does the plan improve or damage order?",
            "score",
            governance_stability,
        ),
        Metric(
            "crisis_resilience",
            "Own strength left at the worst moment",
            "hp",
            crisis_resilience,
        ),
        Metric(
            "commercial_demonstrability",
            "Could the run be shown to an outside client as it is?",
            "checks",
            commercial_demonstrability,
        ),
        Metric(
            "imperial_core_value",
            "Does the run keep the long-term architecture?",
            "checks",
            imperial_core_value,
        ),
    )
}

# Formal Spec 8.3 evaluation_result.scores, in the spec's order
SPEC_SCORES = (
    "physical_possibility",
    "engineering_feasibility",
    "tactical_usefulness",
    "strategic_value",
    "governance_stability",
    "crisis_resilience",
    "resource_efficiency",
    "risk_control",
    "system_robustness",
    "failure_resistance",
    "recovery_ability",
)
# 8.3 names two axes from the cost side: efficiency is resource cost read the
# other way, risk control is risk growth read the other way (both already
# score 1 for the best case)
SPEC_ALIASES = {"resource_efficiency": "resource_cost", "risk_control": "risk_growth"}
