"""Basic actors = five ways to decide, all from an observation, all only proposing.

Important:
Every actor here turns an observation into an order ({action_type, target,
intent, ...}) or None to stand still. None of them sees the world: the
engine hands each its observer's view and issues the action id itself
(development plan Phase 6). Outside code an actor needs — an external
system's client, a language model — is registered by name in code, so a
scenario file can pick one but never load one.
"""

import asyncio
import concurrent.futures
import inspect
import json
import random
import sys
from collections.abc import Callable
from typing import Any, Protocol, TextIO

from ..contracts import ContractError, validate_order
from ..observation.sensing import grid_distance
from ..policies import register_policy
from .queue import ActionQueue

Order = dict[str, Any]
Observation = dict[str, Any]

# ── reading a local observation ──────────────────────────────────────────────


def me(observation: Observation) -> dict[str, Any]:
    """The deciding unit in a local view."""
    for entity in observation["visible_world_state"]["known_entities"]:
        if entity["relation"] == "self":
            return dict(entity)
    raise ValueError("this actor needs a local view (it has no self entry)")


def distance(observation: Observation, a: Any, b: Any) -> float:
    """Distance between two cells under the observation's grid distance model."""
    area = observation["visible_world_state"]["local_area"] or {}
    return grid_distance({"distance_model": area.get("distance_model")}, a, b)


def enemies(observation: Observation, *statuses: str) -> list[dict[str, Any]]:
    """Known enemies with one of statuses, nearest first (then surest, then id)."""
    unit = me(observation)
    found = [
        e
        for e in observation["visible_world_state"]["known_entities"]
        if e["relation"] == "enemy" and e["status"] in statuses and e["position"]
    ]
    if unit["position"] is None:
        return []
    return sorted(
        found,
        key=lambda e: (
            distance(observation, unit["position"], e["position"]),
            -e["confidence"],
            e["entity_id"],
        ),
    )


def step_toward(origin: Any, goal: Any, away: bool = False) -> list[int]:
    """The neighbouring cell one step toward goal (or away from it)."""
    sign = -1 if away else 1
    x, y = origin
    gx, gy = goal
    return [x + sign * ((gx > x) - (gx < x)), y + sign * ((gy > y) - (gy < y))]


def attack(target: dict[str, Any], intent: str) -> Order:
    return {
        "action_type": "attack",
        "target": {"entity_id": target["entity_id"]},
        "intent": intent,
    }


def move(cell: list[int], intent: str) -> Order:
    return {"action_type": "move", "target": {"location": cell}, "intent": intent}


# ── rule-based ───────────────────────────────────────────────────────────────


def _attack_in_range(observation: Observation) -> Order | None:
    unit = me(observation)
    reach = float((unit["capabilities"] or {}).get("attack_range", 1))
    for enemy in enemies(observation, "visible"):
        if distance(observation, unit["position"], enemy["position"]) <= reach:
            return attack(enemy, "rule_attack_in_range")
    return None


def _close_on(observation: Observation, *statuses: str) -> Order | None:
    unit = me(observation)
    targets = enemies(observation, *statuses)
    if not targets:
        return None
    return move(step_toward(unit["position"], targets[0]["position"]), "rule_close_in")


RULES: dict[str, Callable[[Observation], Order | None]] = {
    "attack_in_range": _attack_in_range,
    "close_on_visible": lambda o: _close_on(o, "visible"),
    "close_on_known": lambda o: _close_on(o, "visible", "stale"),
}
HOLD = "hold"


class RuleBasedActor:
    """
    Named rules tried in order; the first that applies decides.

    Important:
    attack_in_range: the nearest visible enemy within the unit's own attack
    range. close_on_visible / close_on_known: one step toward the nearest
    visible (or also remembered) enemy. hold: stop here and stand still.
    No rule applies → stand still.
    """

    def __init__(
        self,
        rules: list[str] | None = None,
        observer: str = "TAC_ANGEL",
        system_id: str = "rule_based",
    ) -> None:
        self.rules = list(rules or ["attack_in_range", "close_on_known"])
        unknown = [r for r in self.rules if r not in RULES and r != HOLD]
        if unknown:
            raise ValueError(f"unknown rules {unknown}; known: {sorted(RULES)}")
        self.observer_profile = observer
        self.system_id = system_id

    def decide_from_observation(self, observation: Observation) -> Order | None:
        for rule in self.rules:
            if rule == HOLD:
                return None
            order = RULES[rule](observation)
            if order is not None:
                return order
        return None


# ── scripted ─────────────────────────────────────────────────────────────────


class ScriptedActor:
    """
    Orders written in advance, by (tick, unit); every other turn stands still.

    Important:
    Each order passes the order contract when the actor is built, so a bad
    script fails before the run starts. Whether an order can be carried out
    is still SKYVAULT's call: a strike out of range is rejected like any other.
    """

    observer_profile = "TAC_ANGEL"

    def __init__(self, orders: list[dict[str, Any]], system_id: str = "scripted"):
        self.system_id = system_id
        self.orders: dict[tuple[int, str], Order] = {}
        for item in orders:
            key = (int(item["tick"]), str(item["entity_id"]))
            if key in self.orders:
                raise ValueError(f"two scripted orders for {key[1]} at tick {key[0]}")
            order = {k: v for k, v in item.items() if k not in ("tick", "entity_id")}
            self.orders[key] = validate_order(order)

    def decide_from_observation(self, observation: Observation) -> Order | None:
        key = (observation["time"], observation["viewpoint"]["actor_id"])
        order = self.orders.get(key)
        return None if order is None else dict(order)


# ── human input ──────────────────────────────────────────────────────────────


class InputSource(Protocol):
    """Where a person's orders come from."""

    def next_order(self, observation: Observation) -> Order | None: ...


class QueueInput:
    """Orders a person submits to an ActionQueue (from a UI thread, say)."""

    def __init__(self, queue: ActionQueue, timeout: float = 30.0) -> None:
        self.queue = queue
        self.timeout = timeout

    def next_order(self, observation: Observation) -> Order | None:
        return self.queue.take(
            observation["time"], observation["viewpoint"]["actor_id"], self.timeout
        )


class ConsoleInput:
    """
    One JSON order per line from a terminal; an empty line stands still.

    Important:
    The prompt shows what the person's observer sees — the observation,
    never the world.
    """

    def __init__(self, reader: TextIO | None = None, writer: TextIO | None = None):
        self.reader = reader or sys.stdin
        self.writer = writer or sys.stdout

    def next_order(self, observation: Observation) -> Order | None:
        unit = observation["viewpoint"]["actor_id"]
        summary = observation["visible_world_state"]["summary"]
        actions = observation["decision_context"]["available_actions"]
        self.writer.write(
            f"tick {observation['time']} {unit}: {json.dumps(summary, sort_keys=True)}"
            f"\nactions {actions}; order as JSON, empty to hold> "
        )
        self.writer.flush()
        line = self.reader.readline().strip()
        if not line:
            return None
        order: Order = json.loads(line)
        return order


class HumanInputActor:
    """A person decides: each turn, the next order from the input source."""

    def __init__(
        self,
        source: InputSource,
        observer: str = "TAC_ANGEL",
        system_id: str = "human_input",
    ) -> None:
        self.source = source
        self.observer_profile = observer
        self.system_id = system_id

    def decide_from_observation(self, observation: Observation) -> Order | None:
        return self.source.next_order(observation)


# ── external system ──────────────────────────────────────────────────────────

Client = Callable[..., Any]
CLIENTS: dict[str, Client] = {}


def register_client(name: str, client: Client) -> None:
    """Make an outside system's client (or a language model's) available by name."""
    existing = CLIENTS.get(name)
    if existing is not None and existing is not client:
        raise ValueError(f"a client named {name!r} is already registered")
    CLIENTS[name] = client


def client_named(name: str) -> Client:
    if name not in CLIENTS:
        known = ", ".join(sorted(CLIENTS)) or "none"
        raise KeyError(f"no client named {name!r} (registered: {known})")
    return CLIENTS[name]


class ExternalSystemActor:
    """
    An outside system decides: its client gets the observation and answers
    with an order, synchronously or as a coroutine.

    Important:
    The answer has to arrive within timeout seconds; a late answer, or a
    client that fails, means the unit stands still this turn — the run
    goes on for everyone else. Both are counted (timeouts, errors).
    """

    def __init__(
        self,
        client: Client,
        timeout: float = 1.0,
        observer: str = "TAC_ANGEL",
        system_id: str = "external_system",
    ) -> None:
        self.client = client
        self.timeout = timeout
        self.observer_profile = observer
        self.system_id = system_id
        self.timeouts = 0
        self.errors = 0

    def decide_from_observation(self, observation: Observation) -> Order | None:
        try:
            if inspect.iscoroutinefunction(self.client):
                answer = asyncio.run(
                    asyncio.wait_for(self.client(observation), self.timeout)
                )
            else:
                # not a with-block: leaving one waits for a late client
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    answer = pool.submit(self.client, observation).result(
                        timeout=self.timeout
                    )
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
        except (TimeoutError, asyncio.TimeoutError, concurrent.futures.TimeoutError):
            self.timeouts += 1
            return None
        except Exception:  # an outside system's failure is not the run's
            self.errors += 1
            return None
        return None if answer is None else dict(answer)


# ── LLM-assisted ─────────────────────────────────────────────────────────────

PROMPT = """You are deciding one action for unit {unit} at tick {tick}.
You see only this observation (JSON):
{observation}
Allowed action types: {actions}.
Answer with one JSON object: {{"action_type": ..., "target": {{"entity_id": ...}} or
{{"location": [x, y]}}, "intent": ...}}, or {{"action_type": null}} to hold."""


class LLMAssistedActor:
    """
    A language model suggests; rules catch what it gets wrong.

    Important:
    The client is any function from a prompt to a reply (no SDK is part of
    SKYVAULT). The first JSON object in the reply is the suggestion. It is
    used only if its action type is allowed, its target is a unit the
    observation knows (or a cell) and it passes the order contract; a reply
    of {"action_type": null} holds. Anything else — no client, no JSON, an
    illegal action, an unknown target — falls back to the rule-based actor,
    and is counted (fallbacks).
    """

    def __init__(
        self,
        client: Callable[[str], str] | None = None,
        fallback: RuleBasedActor | None = None,
        observer: str = "TAC_ANGEL",
        system_id: str = "llm_assisted",
    ) -> None:
        self.client = client
        self.fallback = fallback or RuleBasedActor(observer=observer)
        self.observer_profile = observer
        self.system_id = system_id
        self.suggestions = 0
        self.fallbacks = 0

    def prompt(self, observation: Observation) -> str:
        return PROMPT.format(
            unit=observation["viewpoint"]["actor_id"],
            tick=observation["time"],
            observation=json.dumps(observation, sort_keys=True),
            actions=", ".join(observation["decision_context"]["available_actions"]),
        )

    def decide_from_observation(self, observation: Observation) -> Order | None:
        if self.client is not None:
            suggestion = parse_suggestion(self.client(self.prompt(observation)))
            if suggestion is not None and suggestion.get("action_type") is None:
                self.suggestions += 1
                return None
            if suggestion is not None and acceptable(suggestion, observation):
                self.suggestions += 1
                return suggestion
        self.fallbacks += 1
        return self.fallback.decide_from_observation(observation)


def parse_suggestion(reply: str) -> dict[str, Any] | None:
    """The first JSON object in a reply, or None."""
    decoder = json.JSONDecoder()
    for start, char in enumerate(reply):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(reply[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def acceptable(suggestion: dict[str, Any], observation: Observation) -> bool:
    """An allowed action aimed at a known unit or a cell, in the order contract."""
    if (
        suggestion.get("action_type")
        not in observation["decision_context"]["available_actions"]
    ):
        return False
    target = suggestion.get("target") or {}
    known = {
        e["entity_id"] for e in observation["visible_world_state"]["known_entities"]
    }
    if target.get("entity_id") is not None and target["entity_id"] not in known:
        return False
    try:
        validate_order(suggestion)
    except ContractError:
        return False
    return True


# ── registration ─────────────────────────────────────────────────────────────


def _rule_based(rng: random.Random, params: dict[str, Any]) -> RuleBasedActor:
    return RuleBasedActor(
        params.get("rules"),
        params.get("observer", "TAC_ANGEL"),
        params.get("system_id", "rule_based"),
    )


def _scripted(rng: random.Random, params: dict[str, Any]) -> ScriptedActor:
    return ScriptedActor(params.get("orders", []), params.get("system_id", "scripted"))


def _human_input(rng: random.Random, params: dict[str, Any]) -> HumanInputActor:
    if params.get("source", "console") != "console":
        raise ValueError(
            "by name a human actor reads the console; build others in code"
        )
    return HumanInputActor(ConsoleInput(), params.get("observer", "TAC_ANGEL"))


def _external_system(rng: random.Random, params: dict[str, Any]) -> ExternalSystemActor:
    return ExternalSystemActor(
        client_named(params["client"]),
        float(params.get("timeout", 1.0)),
        params.get("observer", "TAC_ANGEL"),
        params.get("system_id", params["client"]),
    )


def _llm_assisted(rng: random.Random, params: dict[str, Any]) -> LLMAssistedActor:
    client = client_named(params["client"]) if params.get("client") else None
    return LLMAssistedActor(
        client,
        RuleBasedActor(params.get("rules")),
        params.get("observer", "TAC_ANGEL"),
    )


register_policy("rule_based", _rule_based)
register_policy("scripted", _scripted)
register_policy("human_input", _human_input)
register_policy("external_system", _external_system)
register_policy("llm_assisted", _llm_assisted)
