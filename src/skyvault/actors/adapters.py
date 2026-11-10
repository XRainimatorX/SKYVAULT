"""Adapters = each outside system in its own words, translated into orders.

Important:
An adapter hands its system the view that system has (Formal Spec section
5) and translates the system's native answer into an order (adapter
pattern). The real systems are outside SKYVAULT: each adapter takes one as
a callable (native input → native answer) and, without one, uses a small
built-in stand-in so the adapter can run and be tested. A system that
answers in a form its adapter does not know is refused (ValueError): the
contract between SKYVAULT and the system is broken, not the run.

    TAC ANGEL  local           {maneuver: engage | advance | hold, target, waypoint}
    STARTX     aggregate + local  {stance: press | hold | withdraw}
    HADES      threat + local     {response: intercept | monitor, threat}
    AEROGRID   coverage + local   {reposition: true | false}
    SKYFOX     the drone's view   {waypoint: [x, y] | null}

Where a system's view has no positions (STARTX) or no own unit (HADES,
AEROGRID), the system still sees only its view; the unit carries the
answer out with its own local view.
"""

from collections.abc import Callable
from typing import Any

from ..policies import register_policy
from .basic import (
    RuleBasedActor,
    attack,
    distance,
    enemies,
    me,
    move,
    step_toward,
)

Order = dict[str, Any]
Observation = dict[str, Any]
System = Callable[[Observation], dict[str, Any]]


def _known(answer: dict[str, Any], field: str, allowed: tuple[Any, ...]) -> Any:
    value = answer.get(field)
    if value not in allowed:
        raise ValueError(
            f"system answered {field}={value!r}; expected one of {allowed}"
        )
    return value


# ── TAC ANGEL ────────────────────────────────────────────────────────────────


def tac_angel_stand_in(observation: Observation) -> dict[str, Any]:
    """Engage the nearest enemy in range, else advance on the nearest known."""
    unit = me(observation)
    reach = float((unit["capabilities"] or {}).get("attack_range", 1))
    for enemy in enemies(observation, "visible"):
        if distance(observation, unit["position"], enemy["position"]) <= reach:
            return {"maneuver": "engage", "target": enemy["entity_id"]}
    known = enemies(observation, "visible", "stale")
    if known:
        waypoint = step_toward(unit["position"], known[0]["position"])
        return {"maneuver": "advance", "waypoint": waypoint}
    return {"maneuver": "hold"}


class TACAngelAdapter:
    """TAC ANGEL decides the unit's maneuver from its local tactical view."""

    observer_profile = "TAC_ANGEL"
    system_id = "TAC_ANGEL"

    def __init__(self, system: System | None = None) -> None:
        self.system = system or tac_angel_stand_in

    def decide_from_observation(self, observation: Observation) -> Order | None:
        answer = self.system(observation)
        maneuver = _known(answer, "maneuver", ("engage", "advance", "hold"))
        if maneuver == "engage":
            return attack({"entity_id": answer["target"]}, "tac_angel_engage")
        if maneuver == "advance":
            return move(list(answer["waypoint"]), "tac_angel_advance")
        return None


# ── STARTX ───────────────────────────────────────────────────────────────────


def startx_stand_in(observation: Observation) -> dict[str, Any]:
    """Withdraw below a third of the side's health, hold after heavy losses."""
    summary = observation["visible_world_state"]["summary"]
    if summary["own"]["hp_ratio"] < 1 / 3:
        return {"stance": "withdraw"}
    if summary["trend"]["own_hp_ratio_change"] <= -0.2:
        return {"stance": "hold"}
    return {"stance": "press"}


class STARTXBranchAdapter:
    """
    STARTX picks the branch from the trends; each unit carries it out.

    Important:
    The system is handed the STARTX observation only — counts and trends,
    no position and no enemy id. press: fire in range, else close on the
    nearest known enemy. hold: fire in range, never move. withdraw: one
    step away from the nearest known enemy.
    """

    observer_profiles: tuple[str, ...] = ("STARTX", "TAC_ANGEL")
    system_id = "STARTX"

    def __init__(self, system: System | None = None) -> None:
        self.system = system or startx_stand_in
        self.press = RuleBasedActor(["attack_in_range", "close_on_known"])
        self.hold = RuleBasedActor(["attack_in_range", "hold"])

    def decide_from_observations(
        self, observations: dict[str, Observation]
    ) -> Order | None:
        stance = _known(
            self.system(observations["STARTX"]),
            "stance",
            ("press", "hold", "withdraw"),
        )
        local = observations["TAC_ANGEL"]
        if stance == "press":
            return self.press.decide_from_observation(local)
        if stance == "hold":
            return self.hold.decide_from_observation(local)
        known = enemies(local, "visible", "stale")
        if not known:
            return None
        cell = step_toward(me(local)["position"], known[0]["position"], away=True)
        return move(cell, "startx_withdraw")


# ── HADES ────────────────────────────────────────────────────────────────────


def hades_stand_in(observation: Observation) -> dict[str, Any]:
    """
    Intercept the soonest threat to this unit, else the soonest threat to
    the side; with no threat, keep watching.
    """
    unit = observation["viewpoint"]["actor_id"]
    risks = observation["visible_world_state"]["known_risks"]
    mine = [r for r in risks if r["nearest_own"] == unit]
    chosen = (mine or risks)[:1]
    if chosen:
        return {"response": "intercept", "threat": chosen[0]["entity_id"]}
    return {"response": "monitor"}


class HADESAdapter:
    """
    HADES reads the threats; the unit intercepts or keeps watch.

    Important:
    intercept: fire at the threat when it is in sight and in range, else
    step toward it. monitor: an observe action on the unit itself when the
    world offers one, else wait when it offers that, else stand still.
    """

    observer_profiles: tuple[str, ...] = ("HADES", "TAC_ANGEL")
    system_id = "HADES"

    def __init__(self, system: System | None = None) -> None:
        self.system = system or hades_stand_in

    def decide_from_observations(
        self, observations: dict[str, Observation]
    ) -> Order | None:
        answer = self.system(observations["HADES"])
        response = _known(answer, "response", ("intercept", "monitor"))
        local = observations["TAC_ANGEL"]
        unit = me(local)
        if response == "intercept":
            threat = next(
                (
                    e
                    for e in enemies(local, "visible", "stale")
                    if e["entity_id"] == answer.get("threat")
                ),
                None,
            )
            if threat is not None:
                reach = float((unit["capabilities"] or {}).get("attack_range", 1))
                near = distance(local, unit["position"], threat["position"]) <= reach
                if threat["status"] == "visible" and near:
                    return attack(threat, "hades_intercept")
                cell = step_toward(unit["position"], threat["position"])
                return move(cell, "hades_intercept")
        offered = local["decision_context"]["available_actions"]
        for watch in ("observe", "wait"):
            if watch in offered:
                return {
                    "action_type": watch,
                    "target": {"entity_id": unit["entity_id"]},
                    "intent": "hades_monitor",
                }
        return None


# ── AEROGRID ─────────────────────────────────────────────────────────────────


class AEROGRIDAdapter:
    """
    AEROGRID watches coverage; a unit spreads out when coverage is thin.

    Important:
    reposition: one step away from the nearest living ally. Otherwise the
    unit fires at an enemy in range or stands still — AEROGRID tasks
    sensors, it does not hunt.
    """

    observer_profiles: tuple[str, ...] = ("AEROGRID", "TAC_ANGEL")
    system_id = "AEROGRID"

    def __init__(self, system: System | None = None, threshold: float = 0.8) -> None:
        self.threshold = threshold
        self.system = system or self.stand_in
        self.fire = RuleBasedActor(["attack_in_range", "hold"])

    def stand_in(self, observation: Observation) -> dict[str, Any]:
        """Reposition while coverage is below the threshold and gaps remain."""
        summary = observation["visible_world_state"]["summary"]
        thin = summary["coverage_ratio"] < self.threshold and summary["gaps"] > 0
        return {"reposition": thin}

    def decide_from_observations(
        self, observations: dict[str, Observation]
    ) -> Order | None:
        reposition = _known(
            self.system(observations["AEROGRID"]), "reposition", (True, False)
        )
        local = observations["TAC_ANGEL"]
        unit = me(local)
        allies = sorted(
            (
                e
                for e in local["visible_world_state"]["known_entities"]
                if e["relation"] == "ally" and e["status"] == "active" and e["position"]
            ),
            key=lambda e: (
                distance(local, unit["position"], e["position"]),
                e["entity_id"],
            ),
        )
        if reposition and allies:
            cell = step_toward(unit["position"], allies[0]["position"], away=True)
            return move(cell, "aerogrid_reposition")
        return self.fire.decide_from_observation(local)


# ── SKYFOX ───────────────────────────────────────────────────────────────────


class SKYFOXAdapter:
    """
    A SKYFOX drone flies its route, one step a turn, and lands when its energy
    runs low.

    Important:
    route: the waypoints, flown in order and then again from the start.
    A waypoint is reached when the drone stands on it. A drone whose state
    carries energy below energy_floor holds. The system answers with the
    next cell to fly to, or null.
    """

    observer_profile = "SKYFOX"
    system_id = "SKYFOX"

    def __init__(
        self,
        route: list[list[int]] | None = None,
        energy_floor: float = 10.0,
        system: System | None = None,
    ) -> None:
        self.route = [list(cell) for cell in (route or [])]
        self.energy_floor = energy_floor
        self.leg: dict[str, int] = {}
        self.system = system or self.stand_in

    def stand_in(self, observation: Observation) -> dict[str, Any]:
        """The next step along the route; null without a route or with low energy."""
        drone = me(observation)
        energy = (drone["state"] or {}).get("energy")
        if energy is not None and float(energy) < self.energy_floor:
            return {"waypoint": None}
        if not self.route or drone["position"] is None:
            return {"waypoint": None}
        here = list(drone["position"])
        leg = self.leg.get(drone["entity_id"], 0)
        if here == self.route[leg]:
            leg = (leg + 1) % len(self.route)
            self.leg[drone["entity_id"]] = leg
        step = step_toward(here, self.route[leg])
        return {"waypoint": None if step == here else step}

    def decide_from_observation(self, observation: Observation) -> Order | None:
        answer = self.system(observation)
        if "waypoint" not in answer:
            raise ValueError("system answered without a waypoint field")
        if answer["waypoint"] is None:
            return None
        return move(list(answer["waypoint"]), "skyfox_route")


# ── registration ─────────────────────────────────────────────────────────────


register_policy("tac_angel_adapter", lambda rng, params: TACAngelAdapter())
register_policy("startx_branch_adapter", lambda rng, params: STARTXBranchAdapter())
register_policy("hades_adapter", lambda rng, params: HADESAdapter())
register_policy(
    "aerogrid_adapter",
    lambda rng, params: AEROGRIDAdapter(threshold=float(params.get("threshold", 0.8))),
)
register_policy(
    "skyfox_adapter",
    lambda rng, params: SKYFOXAdapter(
        params.get("route"), float(params.get("energy_floor", 10.0))
    ),
)
