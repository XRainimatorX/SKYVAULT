"""The airspace's actions: what the sky does each tick, and what defenders do.

Important:
Upkeep, at the start of every tick: launch (a wave's threats leave
reserve), fly (each threat one tick straight at its target asset; reaching
it is a hit, meeting a drone at its altitude a collision), sense (every
sensor draws once for every flyer in range, and once for a false alarm;
the command node keeps the tracks).

Actors: engage (an interceptor fires a salvo at a track), move (a drone
flies to a cell within its speed — SKYFOX's adapter and the baseline both
use it).

Every random draw comes from the run's generator (context.rng), so the
same seed gives the same sky.
"""

from typing import Any

from ...action import Action
from ...actions import ActionContext, ActionValidation
from ...consequence import Consequence, DirectEffect
from ...world_state import WorldState
from .model import detection_probability, distance, step_toward

ACTION_TYPES = ("launch", "fly", "sense", "engage", "move")
FLYERS = ("threat", "drone")


def cell(position: Any) -> list[int]:
    """A grid position as [x, y]."""
    return [int(position[0]), int(position[1])]


def rules_of(world: WorldState) -> dict[str, Any]:
    rules: dict[str, Any] = world.rules.require("airspace")
    return rules


def of_type(world: WorldState, entity_type: str) -> list[Any]:
    return [e for e in world.entities.values() if e.entity_type == entity_type]


def command_of(world: WorldState) -> Any:
    return next(e for e in world.entities.values() if e.entity_type == "command")


def _done(action: Action, reason: str, effects: list[DirectEffect]) -> Consequence:
    return Consequence(
        action_id=action.action_id, accepted=True, reason=reason, effects=effects
    )


def _effect(
    entity_id: str,
    changes: dict[str, Any],
    tags: list[str],
    data: dict[str, Any] | None = None,
    event_type: str = "ENTITY_STATE_CHANGED",
    affected: list[str] | None = None,
) -> DirectEffect:
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


def _always(world: WorldState, action: Action, context: ActionContext):
    return ActionValidation.ok()


class LaunchHandler:
    """
    launch: a threat (target.entity_id) leaves reserve at its launch cell.
    The command node issues it: a threat in reserve is not active, and the
    resolver takes no action from an inactive actor.
    """

    action_type = "launch"
    validate = staticmethod(_always)

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        threat = world.get_entity(str(action.target.entity_id))
        return _done(
            action,
            "Launch resolved",
            [
                _effect(
                    threat.entity_id,
                    {"state": {"status": "active"}},
                    ["launch", "state_change"],
                    {"wave": threat.state["wave"], "at": cell(threat.position)},
                )
            ],
        )


class FlyHandler:
    """
    fly: a threat moves speed cells straight at its target asset. A
    fractional speed carries over (state.carry): 1.25 is one cell a tick
    and a second every fourth tick. On the asset it hits: the asset takes a
    hit (destroyed at rules.asset.hits_to_destroy) and the threat is spent
    ("leaked"). Ending on a cell with a drone at its altitude is a
    collision: both are destroyed.
    """

    action_type = "fly"
    validate = staticmethod(_always)

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        threat = world.get_entity(action.actor_id)
        asset = world.get_entity(threat.state["target"])
        here = cell(threat.position)
        flown = float(threat.state.get("carry", 0.0)) + float(
            threat.capabilities["speed"]
        )
        cells = int(flown)
        there = step_toward(here, asset.position, cells)
        effects = [
            _effect(
                threat.entity_id,
                {"position": there, "state": {"carry": round(flown - cells, 6)}},
                ["fly", "world_state_mutation"],
                {"from": here, "to": there},
                event_type="MOVE",
            )
        ]
        if there == cell(asset.position):
            hits = int(asset.state["hits"]) + 1
            destroyed = hits >= int(rules_of(world)["asset"]["hits_to_destroy"])
            effects.append(
                _effect(
                    threat.entity_id,
                    {"state": {"status": "leaked"}},
                    ["leak", "state_change"],
                    {"target": asset.entity_id},
                )
            )
            effects.append(
                _effect(
                    asset.entity_id,
                    {
                        "state": {
                            "hits": hits,
                            **({"status": "destroyed"} if destroyed else {}),
                        }
                    },
                    ["asset_hit", "state_change"],
                    {"by": threat.entity_id, "hits": hits, "destroyed": destroyed},
                    affected=[threat.entity_id, asset.entity_id],
                )
            )
            return _done(action, "Fly resolved: hit", effects)
        drone = next(
            (
                d
                for d in of_type(world, "drone")
                if d.is_active()
                and cell(d.position) == there
                and d.state["altitude"] == threat.state["altitude"]
            ),
            None,
        )
        if drone is not None:
            for victim, other in ((drone, threat), (threat, drone)):
                effects.append(
                    _effect(
                        victim.entity_id,
                        {"state": {"status": "destroyed"}},
                        ["collision", "state_change"],
                        {"with": other.entity_id, "cause": "collision"},
                        event_type="ENTITY_DESTROYED",
                        affected=[drone.entity_id, threat.entity_id],
                    )
                )
        return _done(action, "Fly resolved", effects)


class SenseHandler:
    """
    sense: every online sensor draws once for every active flyer in range
    (detection_probability) and once for a false alarm (a phantom at a
    random cell in its range). The command node then keeps its tracks:

    a first detection opens a track, identified correctly with probability
    command.identify (a drone misidentified is a threat to the defence, a
    threat misidentified is let through); a track may be fired on from
    command.reaction_delay ticks after it opened; one not seen for more
    than command.track_timeout ticks, or whose target is gone, is dropped.
    A phantom is always taken for a threat.
    """

    action_type = "sense"
    validate = staticmethod(_always)

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        rules = rules_of(world)
        command = rules["command"]
        falloff = float(rules["detection"]["falloff"])
        node = command_of(world)
        tracks = {k: dict(v) for k, v in node.state["tracks"].items()}
        next_track = int(node.state["next_track"])
        tick = world.tick
        flyers = [
            e
            for e in world.entities.values()
            if e.entity_type in FLYERS and e.is_active()
        ]
        width, height = (int(n) for n in rules["size"])
        detections: list[dict[str, Any]] = []
        phantoms: list[dict[str, Any]] = []
        for sensor in of_type(world, "sensor"):
            if not sensor.state["online"]:
                continue
            spec = {"at": sensor.position, **sensor.capabilities}
            for flyer in flyers:
                p = detection_probability(
                    spec, flyer.position, flyer.state.get("altitude", "medium"), falloff
                )
                if p > 0 and context.rng.random() < p:
                    detections.append(
                        {"sensor": sensor.entity_id, "target": flyer.entity_id, "p": p}
                    )
            if context.rng.random() < float(sensor.capabilities["false_alarm"]):
                reach = int(sensor.capabilities["range"])
                x, y = sensor.position
                spot = [
                    min(width - 1, max(0, x + context.rng.randint(-reach, reach))),
                    min(height - 1, max(0, y + context.rng.randint(-reach, reach))),
                ]
                phantoms.append({"sensor": sensor.entity_id, "at": spot})

        by_target = {t["target"]: key for key, t in tracks.items() if t["target"]}
        opened: list[str] = []
        seen: dict[str, float] = {}
        for found in detections:
            seen[found["target"]] = max(seen.get(found["target"], 0.0), found["p"])
        for target_id, p in sorted(seen.items()):
            target = world.get_entity(target_id)
            if target_id in by_target:
                track = tracks[by_target[target_id]]
                track.update(
                    last_seen=tick, position=cell(target.position), confidence=p
                )
                continue
            kind = "threat" if target.entity_type == "threat" else "friend"
            right = context.rng.random() < float(command["identify"])
            identified = kind if right else ("friend" if kind == "threat" else "threat")
            key = f"T{next_track}"
            next_track += 1
            tracks[key] = {
                "track_id": key,
                "target": target_id,
                "kind": kind,
                "identified": identified,
                "opened": tick,
                "last_seen": tick,
                "engageable_from": tick + int(command["reaction_delay"]),
                "position": cell(target.position),
                "confidence": p,
                "engaged": 0,
            }
            opened.append(key)
        for phantom in phantoms:
            key = f"T{next_track}"
            next_track += 1
            tracks[key] = {
                "track_id": key,
                "target": None,
                "kind": "false",
                "identified": "threat",
                "opened": tick,
                "last_seen": tick,
                "engageable_from": tick + int(command["reaction_delay"]),
                "position": phantom["at"],
                "confidence": 0.5,
                "engaged": 0,
            }
            opened.append(key)
        timeout = int(command["track_timeout"])
        lost = sorted(
            key
            for key, t in tracks.items()
            if tick - int(t["last_seen"]) > timeout
            or (t["target"] and not world.get_entity(t["target"]).is_active())
        )
        for key in lost:
            del tracks[key]
        return _done(
            action,
            "Sense resolved",
            [
                _effect(
                    node.entity_id,
                    {"state": {"tracks": tracks, "next_track": next_track}},
                    ["sense", "state_change"],
                    {
                        "detections": detections,
                        "false_alarms": phantoms,
                        "opened": opened,
                        "lost": lost,
                        "tracks": sorted(tracks),
                    },
                )
            ],
        )


class EngageHandler:
    """
    engage: an interceptor fires a salvo (action.metadata.shots, at most its
    ammo) at the track action.metadata.track. Each shot hits with the
    interceptor's kill probability when the track is real and its target is
    within range now; the first hit destroys the target (a friend so
    destroyed is fratricide). A phantom absorbs the salvo. The interceptor
    then reloads for its reload ticks.
    """

    action_type = "engage"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type != "interceptor":
            return ActionValidation.reject("Only interceptors engage")
        if int(actor.state["ammo"]) <= 0:
            return ActionValidation.reject("Out of ammunition")
        if world.tick < int(actor.state["ready_at"]):
            return ActionValidation.reject("Reloading")
        track = command_of(world).state["tracks"].get(action.metadata.get("track"))
        if track is None:
            return ActionValidation.reject("No such track")
        if world.tick < int(track["engageable_from"]):
            return ActionValidation.reject("Track not cleared to engage yet")
        if distance(actor.position, track["position"]) > float(
            actor.capabilities["range"]
        ):
            return ActionValidation.reject("Track out of range")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        node = command_of(world)
        key = action.metadata["track"]
        track = dict(node.state["tracks"][key])
        shots = max(
            1, min(int(action.metadata.get("shots", 1)), int(actor.state["ammo"]))
        )
        target = world.entities.get(track["target"]) if track["target"] else None
        reachable = (
            target is not None
            and target.is_active()
            and distance(actor.position, target.position)
            <= float(actor.capabilities["range"])
        )
        kill = float(actor.capabilities["kill"])
        rolls = [context.rng.random() < kill for _ in range(shots)]
        hit = reachable and any(rolls)
        tracks = {k: dict(v) for k, v in node.state["tracks"].items()}
        tracks[key]["engaged"] = int(tracks[key]["engaged"]) + 1
        if hit:
            del tracks[key]
        about = {
            "track": key,
            "kind": track["kind"],
            "identified": track["identified"],
            "shots": shots,
            "hit": hit,
        }
        effects = [
            _effect(
                actor.entity_id,
                {
                    "state": {
                        "ammo": int(actor.state["ammo"]) - shots,
                        "ready_at": world.tick + int(actor.capabilities["reload"]),
                    }
                },
                ["engage", "state_change"],
                about,
            ),
            _effect(
                node.entity_id,
                {"state": {"tracks": tracks}},
                ["engage", "track", "state_change"],
                about,
            ),
        ]
        if hit and target is not None:
            cause = "intercepted" if track["kind"] == "threat" else "fratricide"
            effects.append(
                _effect(
                    target.entity_id,
                    {"state": {"status": "destroyed"}},
                    ["intercept", cause, "state_change"],
                    {**about, "cause": cause},
                    event_type="ENTITY_DESTROYED",
                    affected=[actor.entity_id, target.entity_id],
                )
            )
        else:
            effects.append(
                DirectEffect(
                    group="entity",
                    event_type="MISS",
                    entity_id=actor.entity_id,
                    changes={},
                    target_entity_id=track["target"],
                    affected_entities=[actor.entity_id],
                    data=about,
                    tags=["engage", "miss"],
                )
            )
        return _done(action, "Engage resolved", effects)


class MoveHandler:
    """move: a drone flies to target.location, within its speed (Chebyshev)."""

    action_type = "move"

    def validate(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> ActionValidation:
        actor = world.get_entity(action.actor_id)
        if actor.entity_type != "drone":
            return ActionValidation.reject("Only drones fly on orders")
        goal = action.target.location
        if goal is None or not world.space.is_inside(goal):
            return ActionValidation.reject("Move target outside the airspace")
        if distance(actor.position, goal) > int(actor.capabilities["speed"]):
            return ActionValidation.reject("Move target out of reach")
        return ActionValidation.ok()

    def resolve(
        self, world: WorldState, action: Action, context: ActionContext
    ) -> Consequence:
        actor = world.get_entity(action.actor_id)
        goal = cell(action.target.location)
        here = cell(actor.position)
        route = actor.capabilities.get("route") or [goal]
        leg = int(actor.state.get("leg", 0)) % len(route)
        if here == list(route[leg]):
            leg = (leg + 1) % len(route)
        if goal == list(route[leg]):
            leg = (leg + 1) % len(route)
        return _done(
            action,
            "Move resolved",
            [
                _effect(
                    actor.entity_id,
                    {"position": goal, "state": {"leg": leg}},
                    ["move", "world_state_mutation"],
                    {"from": here, "to": goal},
                    event_type="MOVE",
                )
            ],
        )


def airspace_handlers() -> dict[str, Any]:
    handlers = (
        LaunchHandler(),
        FlyHandler(),
        SenseHandler(),
        EngageHandler(),
        MoveHandler(),
    )
    return {handler.action_type: handler for handler in handlers}
