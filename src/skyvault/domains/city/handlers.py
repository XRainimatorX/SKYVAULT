"""The city's actions: what its actors do, and what the city does by itself each tick.

Important:
Actors: travel (police, convoys' return and repair crews move along roads
and arrive later), patrol (police raise public order where they stand),
dispatch (a convoy loads food at its depot and sets out for a district),
restore_power (a repair crew works on an offline substation), administer
(the city office strengthens the weakest administration).

Upkeep, in this order at the start of every tick: power_update (incidents,
overload trips, who is fed power), arrive (whoever's trip ends now),
district_update (each district eats, and its public order moves). Every
change is an effect, so every change is an event with the action's id.
"""

from typing import Any

from ...action import Action
from ...actions import ActionContext, ActionValidation
from ...consequence import Consequence, DirectEffect
from ...world_state import WorldState
from .model import consumption, demand, eta, order_delta, order_state, power_flow

ACTION_TYPES = (
    "travel",
    "patrol",
    "dispatch",
    "restore_power",
    "administer",
    "power_update",
    "arrive",
    "district_update",
)
MOBILE = ("police", "convoy", "repair_crew")


def rules_of(world: WorldState) -> dict[str, Any]:
    """The city rules the scenario carries."""
    rules: dict[str, Any] = world.rules.require("city")
    return rules


def districts(world: WorldState) -> list[Any]:
    """Every district, in registry order."""
    return [e for e in world.entities.values() if e.entity_type == "district"]


def of_type(world: WorldState, entity_type: str) -> list[Any]:
    return [e for e in world.entities.values() if e.entity_type == entity_type]


def _done(action: Action, reason: str, effects: list[DirectEffect]) -> Consequence:
    return Consequence(
        action_id=action.action_id, accepted=True, reason=reason, effects=effects
    )


def _state(
    entity_id: str,
    state: dict[str, Any],
    tags: list[str],
    data: dict[str, Any] | None = None,
    event_type: str = "ENTITY_STATE_CHANGED",
    position: Any = ...,
    affected: list[str] | None = None,
) -> DirectEffect:
    changes: dict[str, Any] = {"state": state}
    if position is not ...:
        changes["position"] = position
    return DirectEffect(
        group="entity",
        event_type=event_type,
        entity_id=entity_id,
        changes=changes,
        target_entity_id=entity_id,
        affected_entities=affected or [entity_id],
        data=data or {},
        tags=tags,
    )


# ── what actors do ───────────────────────────────────────────────────────────


class TravelHandler:
    """
    travel: set out along the roads for target.location; the trip takes
    eta(route, factor) ticks, and the traveller is on the road (no
    position) until it arrives. Convoys travel slower by the supply delay
    factor; everyone else at factor 1.
    """

    action_type = "travel"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type not in MOBILE:
            return ActionValidation.reject(f"A {actor.entity_type} does not travel")
        if actor.position is None:
            return ActionValidation.reject("Already on the road")
        goal = action.target.location
        if goal is None or not world.space.is_inside(goal):
            return ActionValidation.reject("Travel needs a place in the city")
        if goal == actor.position:
            return ActionValidation.reject("Already there")
        if world.space.distance(actor.position, goal) == float("inf"):
            return ActionValidation.reject("No road leads there")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        goal = action.target.location
        factor = (
            float(rules_of(world)["supply"]["delay_factor"])
            if actor.entity_type == "convoy"
            else 1.0
        )
        ticks = eta(world.space.distance(actor.position, goal), factor)
        return _done(
            action,
            "Travel resolved",
            [
                _state(
                    actor.entity_id,
                    {
                        "destination": goal,
                        "arrives_at": world.tick + ticks,
                        "origin": actor.position,
                    },
                    ["travel", "departure", "world_state_mutation"],
                    {"from": actor.position, "to": goal, "ticks": ticks},
                    position=None,
                )
            ],
        )


class PatrolHandler:
    """
    patrol: police raise public order in the district they stand in, by a
    draw from rules.order.patrol (at most 100).
    """

    action_type = "patrol"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type != "police":
            return ActionValidation.reject("Only police patrol")
        if actor.position is None:
            return ActionValidation.reject("On the road, not in a district")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        district = world.get_entity(str(actor.position))
        low, high = rules_of(world)["order"]["patrol"]
        gain = round(context.rng.uniform(float(low), float(high)), 4)
        before = float(district.state["public_order"])
        after = min(100.0, round(before + gain, 4))
        rules = rules_of(world)
        return _done(
            action,
            "Patrol resolved",
            [
                _state(
                    district.entity_id,
                    {"public_order": after, "order_state": order_state(after, rules)},
                    ["patrol", "public_order", "state_change"],
                    {
                        "gain": round(after - before, 4),
                        "from_state": district.state["order_state"],
                        "to_state": order_state(after, rules),
                    },
                    affected=[actor.entity_id, district.entity_id],
                )
            ],
        )


class DispatchHandler:
    """
    dispatch: a convoy at its home depot loads what the depot can give (up
    to its capacity) and sets out for the district target.entity_id. It
    arrives after eta(route, supply delay factor) ticks — at least one.
    """

    action_type = "dispatch"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type != "convoy":
            return ActionValidation.reject("Only convoys are dispatched")
        if actor.position is None or actor.position != actor.state["home"]:
            return ActionValidation.reject("A convoy loads only at its home depot")
        depot = _depot_at(world, actor.position)
        if depot is None or float(depot.state["food"]) <= 0:
            return ActionValidation.reject("The depot is empty")
        target = world.entities.get(str(action.target.entity_id))
        if target is None or target.entity_type != "district":
            return ActionValidation.reject("Dispatch needs a district")
        if world.space.distance(actor.position, target.position) == float("inf"):
            return ActionValidation.reject("No road leads there")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        depot = _depot_at(world, actor.position)
        if depot is None:  # pragma: no cover - validate refuses this
            raise ValueError("dispatch from a place without a depot")
        target = world.get_entity(str(action.target.entity_id))
        cargo = round(
            min(float(actor.capabilities["capacity"]), float(depot.state["food"])), 4
        )
        factor = float(rules_of(world)["supply"]["delay_factor"])
        # a delivery takes at least a tick, even next door: arrivals for this
        # tick have already happened
        ticks = max(
            1, eta(world.space.distance(actor.position, target.position), factor)
        )
        return _done(
            action,
            "Dispatch resolved",
            [
                _state(
                    depot.entity_id,
                    {"food": round(float(depot.state["food"]) - cargo, 4)},
                    ["dispatch", "supply", "state_change"],
                    {"loaded": cargo, "convoy": actor.entity_id},
                    affected=[depot.entity_id, actor.entity_id],
                ),
                _state(
                    actor.entity_id,
                    {
                        "cargo": cargo,
                        "destination": target.position,
                        "arrives_at": world.tick + ticks,
                        "leg": "outbound",
                        "origin": actor.position,
                        "dispatched_at": world.tick,
                    },
                    ["dispatch", "travel", "departure", "world_state_mutation"],
                    {
                        "from": actor.position,
                        "to": target.position,
                        "ticks": ticks,
                        "cargo": cargo,
                    },
                    position=None,
                    affected=[actor.entity_id, target.entity_id],
                ),
            ],
        )


class RestorePowerHandler:
    """
    restore_power: a repair crew standing at an offline substation works on
    it; when the work done reaches the work needed, it is back online.
    """

    action_type = "restore_power"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type != "repair_crew":
            return ActionValidation.reject("Only repair crews restore power")
        target = world.entities.get(str(action.target.entity_id))
        if target is None or target.entity_type != "substation":
            return ActionValidation.reject("Restore power needs a substation")
        if target.state["online"]:
            return ActionValidation.reject("The substation is already online")
        if actor.position != target.position:
            return ActionValidation.reject("The crew is not at the substation")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        target = world.get_entity(str(action.target.entity_id))
        done = int(target.state["repair_done"]) + 1
        online = done >= int(target.state["repair_needed"])
        state: dict[str, Any] = {"repair_done": done}
        if online:
            state.update(
                {
                    "online": True,
                    "overloaded": False,
                    "outage": None,
                    "repair_needed": 0,
                    "repair_done": 0,
                }
            )
        return _done(
            action,
            "Restore power resolved",
            [
                _state(
                    target.entity_id,
                    state,
                    ["power", "repair", "state_change"]
                    + (["restored"] if online else []),
                    {
                        "work_done": done,
                        "work_needed": int(target.state["repair_needed"]),
                        "online": online,
                    },
                    event_type="REPAIR",
                    affected=[action.actor_id, target.entity_id],
                )
            ],
        )


class AdministerHandler:
    """administer: the city office raises one district's administration (at most 1)."""

    action_type = "administer"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type != "city_office":
            return ActionValidation.reject("Only the city office administers")
        target = world.entities.get(str(action.target.entity_id))
        if target is None or target.entity_type != "district":
            return ActionValidation.reject("Administer needs a district")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        target = world.get_entity(str(action.target.entity_id))
        step = float(rules_of(world)["recovery"]["administer"])
        after = round(min(1.0, float(target.state["administration"]) + step), 4)
        return _done(
            action,
            "Administer resolved",
            [
                _state(
                    target.entity_id,
                    {"administration": after},
                    ["administer", "state_change"],
                    {"administration": after},
                    affected=[action.actor_id, target.entity_id],
                )
            ],
        )


# ── what the city does by itself ─────────────────────────────────────────────


class PowerUpdateHandler:
    """
    power_update: the grid at the start of a tick.

    Important:
    1. Incidents for this tick take their substation offline.
    2. A substation that was overloaded at the last update and still is
       trips (protection acts after one tick of strain): offline, and its
       trip records the outage that sent it the load (caused_by_event). A
       failed substation's districts move to its backups; a tripped one's
       stay dark until it is reset (power_flow's transfers).
    3. A substation newly over capacity is marked overloaded (strain).
    4. Every district whose supply changes records it.
    Offline substations need repair: rules.repair.failure_ticks of work
    after an incident, trip_ticks after an overload trip.
    """

    action_type = "power_update"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        rules = rules_of(world)
        subs = {s.entity_id: s for s in of_type(world, "substation")}
        grid = {
            sub_id: {
                "capacity": float(s.capabilities["capacity"]),
                "serves": list(s.capabilities["serves"]),
                "backup": list(s.capabilities["backup"]),
                "online": bool(s.state["online"]),
                "transfers": s.state.get("outage") != "trip",
            }
            for sub_id, s in subs.items()
        }
        loads = {
            d.entity_id: demand(d.state["population"], rules) for d in districts(world)
        }
        effects: list[DirectEffect] = []

        for incident in rules.get("incidents", []):
            target = incident["target"]
            if int(incident["tick"]) == world.tick and grid[target]["online"]:
                grid[target]["online"] = False
                effects.append(
                    _state(
                        target,
                        {
                            "online": False,
                            "overloaded": False,
                            "outage": "failure",
                            "repair_needed": int(rules["repair"]["failure_ticks"]),
                            "repair_done": 0,
                        },
                        ["power", "failure", "state_change"],
                        {"cause": "incident", "incident": incident["type"]},
                    )
                )

        before = power_flow(grid, loads)
        for sub_id in before["overloaded"]:
            if subs[sub_id].state["overloaded"]:
                grid[sub_id]["online"] = False
                grid[sub_id]["transfers"] = False
                sources = sorted(
                    {
                        before["moved"][d]
                        for d, feeder in before["feeds"].items()
                        if feeder == sub_id and d in before["moved"]
                    }
                )
                effects.append(
                    _state(
                        sub_id,
                        {
                            "online": False,
                            "overloaded": False,
                            "outage": "trip",
                            "repair_needed": int(rules["repair"]["trip_ticks"]),
                            "repair_done": 0,
                        },
                        ["power", "trip", "cascade", "state_change"],
                        {
                            "cause": "overload",
                            "load": before["load"][sub_id],
                            "capacity": grid[sub_id]["capacity"],
                            "load_from": sources,
                            "caused_by_event": [
                                _last_outage(world, source) for source in sources
                            ],
                        },
                    )
                )

        after = power_flow(grid, loads)
        for sub_id, s in subs.items():
            strained = sub_id in after["overloaded"]
            if grid[sub_id]["online"] and (
                strained != bool(s.state["overloaded"])
                or after["load"][sub_id] != float(s.state["load"])
            ):
                effects.append(
                    _state(
                        sub_id,
                        {"overloaded": strained, "load": after["load"][sub_id]},
                        ["power", "load"] + (["overload"] if strained else []),
                        {
                            "load": after["load"][sub_id],
                            "capacity": grid[sub_id]["capacity"],
                        },
                    )
                )

        for district in districts(world):
            feeder = after["feeds"].get(district.entity_id)
            powered = int(feeder is not None)
            if (
                powered != int(district.state["power"])
                or feeder != district.state["substation"]
            ):
                effects.append(
                    _state(
                        district.entity_id,
                        {
                            "power": powered,
                            "substation": feeder,
                            "communication": (
                                1.0
                                if powered
                                else float(rules["power"]["dark_communication"])
                            ),
                        },
                        ["power", "state_change"] + ([] if powered else ["blackout"]),
                        {"substation": feeder, "powered": bool(powered)},
                    )
                )
        return _done(action, "Power update resolved", effects)


class ArriveHandler:
    """
    arrive: the actor's trip ends this tick. Police and crews stand at
    their destination. A convoy on its way out unloads into the district
    there (a SUPPLY event) and starts back home; one coming home is ready
    for the next load.
    """

    action_type = "arrive"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.state.get("arrives_at") != world.tick:
            return ActionValidation.reject("Not arriving now")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        here = actor.state["destination"]
        idle: dict[str, Any] = {"destination": None, "arrives_at": None}
        if actor.entity_type != "convoy" or actor.state["leg"] == "returning":
            if actor.entity_type == "convoy":
                idle["leg"] = "idle"
            return _done(
                action,
                "Arrival resolved",
                [
                    _state(
                        actor.entity_id,
                        idle,
                        ["arrive", "world_state_mutation"],
                        {"from": actor.state.get("origin"), "to": here},
                        event_type="MOVE",
                        position=here,
                    )
                ],
            )
        district = world.get_entity(str(here))
        cargo = float(actor.state["cargo"])
        home = actor.state["home"]
        factor = float(rules_of(world)["supply"]["delay_factor"])
        back = max(1, eta(world.space.distance(here, home), factor))
        return _done(
            action,
            "Delivery resolved",
            [
                _state(
                    district.entity_id,
                    {"food": round(float(district.state["food"]) + cargo, 4)},
                    ["supply", "delivery", "state_change"],
                    {
                        "delivered": cargo,
                        "convoy": actor.entity_id,
                        "dispatched_at": actor.state.get("dispatched_at"),
                    },
                    event_type="SUPPLY",
                    affected=[actor.entity_id, district.entity_id],
                ),
                _state(
                    actor.entity_id,
                    {
                        "cargo": 0.0,
                        "destination": home,
                        "arrives_at": world.tick + back,
                        "leg": "returning",
                        "origin": here,
                    },
                    ["travel", "departure", "world_state_mutation"],
                    {"from": here, "to": home, "ticks": back},
                    position=None,
                ),
            ],
        )


class DistrictUpdateHandler:
    """
    district_update: one district's tick — it eats, its industry and
    administration drift with power and order, and its public order moves
    by order_delta plus a small draw (rules.order.noise). A change of band
    is recorded as from_state → to_state.
    """

    action_type = "district_update"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        target = world.entities.get(str(action.target.entity_id))
        if target is None or target.entity_type != "district":
            return ActionValidation.reject("Not a district")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        rules = rules_of(world)
        district = world.get_entity(str(action.target.entity_id))
        state = district.state
        eaten = round(consumption(state["population"], rules), 4)
        food_left = round(max(0.0, float(state["food"]) - eaten), 4)
        powered = bool(state["power"])
        dark_medical = float(rules["power"]["dark_medical"])
        medical = float(state["medical"]) * (1.0 if powered else dark_medical)
        administration = float(state["administration"]) * float(state["communication"])
        neighbours = set(world.space.neighbors(district.position))
        riot_next_door = any(
            d.state["order_state"] == "riot"
            for d in districts(world)
            if d.position in neighbours
        )
        parts = order_delta(
            {
                "food_left": food_left,
                "eaten": eaten,
                "powered": powered,
                "medical": medical,
                "administration": administration,
                "population": float(state["population"]),
                "riot_next_door": riot_next_door,
            },
            rules,
        )
        noise = float(rules["order"]["noise"])
        parts["noise"] = round(context.rng.uniform(-noise, noise), 4)
        before = float(state["public_order"])
        after = round(min(100.0, max(0.0, before + parts["total"] + parts["noise"])), 4)
        band = order_state(after, rules)
        recovery = rules["recovery"]
        working = powered and band in ("stable", "tense")
        industry = float(state["industry"]) + (
            recovery["industry_up"] if working else -recovery["industry_down"]
        )
        admin = float(state["administration"]) + (
            recovery["administration_up"]
            if band == "stable"
            else -recovery["administration_down"] if band == "riot" else 0.0
        )
        return _done(
            action,
            "District update resolved",
            [
                _state(
                    district.entity_id,
                    {
                        "food": food_left,
                        "public_order": after,
                        "order_state": band,
                        "industry": round(min(1.0, max(0.0, industry)), 4),
                        "administration": round(min(1.0, max(0.0, admin)), 4),
                    },
                    ["district_update", "public_order", "state_change"],
                    {
                        "eaten": eaten,
                        "order_parts": parts,
                        "from_state": state["order_state"],
                        "to_state": band,
                        "medical_effective": round(medical, 4),
                    },
                )
            ],
        )


def _depot_at(world: WorldState, place: Any) -> Any:
    return next((d for d in of_type(world, "depot") if d.position == place), None)


def _last_outage(world: WorldState, substation: str) -> str | None:
    """The event in which substation last went offline."""
    for event in reversed(world.event_memory):
        if (
            event.target_entity_id == substation
            and "power" in event.tags
            and ("failure" in event.tags or "trip" in event.tags)
        ):
            return str(event.event_id)
    return None


def city_handlers() -> dict[str, Any]:
    """Every handler the city resolves actions with, by action type."""
    handlers = (
        TravelHandler(),
        PatrolHandler(),
        DispatchHandler(),
        RestorePowerHandler(),
        AdministerHandler(),
        PowerUpdateHandler(),
        ArriveHandler(),
        DistrictUpdateHandler(),
    )
    return {handler.action_type: handler for handler in handlers}
