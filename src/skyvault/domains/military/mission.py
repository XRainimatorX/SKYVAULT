"""Mission outcome = did each faction do what its mission asked, judged after the run.

Important:
Pure: it reads the result package's final world and the scenario's
missions, imports nothing that runs a simulation, and leaves the core
evaluation untouched. A seize or hold is judged on who stands on the
objective when the run ends.
"""

from typing import Any


def mission_outcome(
    package: dict[str, Any], scenario: dict[str, Any]
) -> dict[str, Any]:
    """{faction: {type, achieved, reason}} for every faction with a mission."""
    factions = scenario["world_contract"]["rule_set"]["military"]["factions"]
    units = package["final_world_state"]["entities"].values()
    alive = [u for u in units if u["state"].get("status", "active") == "active"]
    end_tick = package["final_world_state"]["tick"]
    outcome = {}
    for faction, side in factions.items():
        mission = side["mission"]
        own = [u for u in alive if u["faction"] == faction]
        enemies = [u for u in alive if u["faction"] != faction]
        objective = {tuple(cell) for cell in mission.get("objective", [])}
        on = {
            "own": [u for u in own if tuple(u["position"] or ()) in objective],
            "enemy": [u for u in enemies if tuple(u["position"] or ()) in objective],
        }
        kind = mission["type"]
        if kind == "destroy":
            achieved = not enemies
            reason = (
                "every enemy unit destroyed"
                if achieved
                else f"{len(enemies)} enemy units still active"
            )
        elif kind == "seize":
            achieved = bool(on["own"]) and not on["enemy"]
            reason = _objective_reason(on, achieved, "holds the objective")
        elif kind == "hold":
            achieved = bool(own) and not on["enemy"]
            reason = (
                "no enemy on the objective"
                if achieved
                else (
                    "no own unit left"
                    if not own
                    else "an enemy stands on the objective"
                )
            )
        else:  # delay
            deadline = int(mission.get("deadline", end_tick))
            achieved = bool(own) and end_tick >= deadline
            reason = (
                f"units still active at tick {end_tick} (deadline {deadline})"
                if achieved
                else (
                    "no own unit left"
                    if not own
                    else f"run ended at tick {end_tick}, before the deadline {deadline}"
                )
            )
        outcome[faction] = {"type": kind, "achieved": achieved, "reason": reason}
    return outcome


def _objective_reason(on: dict[str, list[Any]], achieved: bool, success: str) -> str:
    if achieved:
        return f"{len(on['own'])} own unit(s) on the objective; {success}"
    if on["enemy"]:
        return f"{len(on['enemy'])} enemy unit(s) still on the objective"
    return "no own unit on the objective"
