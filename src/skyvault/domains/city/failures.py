"""What the core failure variables mean in a city (Formal Spec section 14).

Important:
Same names, same four levels, same place in a failure map — the city's
own model underneath:

supply_delay        convoys travel slower: supply.delay_factor × 1.25 / 1.5 / 2 / 3
civilian_pressure   public order starts lower: × 0.9 / 0.75 / 0.6 / 0.4
resource_shortage   the depots hold less food: × 0.75 / 0.5 / 0.25 / 0
public_order_collapse  order stops holding (Formal Spec 2.3): recovery
                    × 0.75 / 0.5 / 0.25 / 0 and riots spread to neighbours
                    × 1.5 / 2 / 3 / 4

The other variables keep their core meaning (communication_failure drops
orders anywhere; the combat ones do not apply to a city without weapons).
"""

from typing import Any

from ...failure.variables import STRESS_LEVELS, FailureVariable
from .model import order_state

DELAY = (1.25, 1.5, 2.0, 3.0)
ORDER = (0.9, 0.75, 0.6, 0.4)
STOCK = (0.75, 0.5, 0.25, 0.0)
RECOVERY = (0.75, 0.5, 0.25, 0.0)
CONTAGION = (1.5, 2.0, 3.0, 4.0)


def _of(scenario: dict[str, Any], entity_type: str) -> list[dict[str, Any]]:
    return [e for e in scenario["entities"] if e["entity_type"] == entity_type]


def _needs(entity_type: str, what: str) -> Any:
    def applies(scenario: dict[str, Any], perspective: str) -> tuple[bool, str]:
        if _of(scenario, entity_type):
            return True, ""
        return False, f"the city has no {what}"

    return applies


def _delay(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    supply = scenario["world_contract"]["rule_set"]["city"]["supply"]
    factor = DELAY[STRESS_LEVELS.index(level)]
    supply["delay_factor"] = round(float(supply["delay_factor"]) * factor, 4)
    return scenario


def _pressure(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    rules = scenario["world_contract"]["rule_set"]["city"]
    factor = ORDER[STRESS_LEVELS.index(level)]
    for district in _of(scenario, "district"):
        order = round(float(district["state"]["public_order"]) * factor, 4)
        district["state"]["public_order"] = order
        district["state"]["order_state"] = order_state(order, rules)
    return scenario


def _collapse(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    order = scenario["world_contract"]["rule_set"]["city"]["order"]
    index = STRESS_LEVELS.index(level)
    order["recovery"] = round(float(order["recovery"]) * RECOVERY[index], 4)
    order["riot_neighbour"] = round(
        float(order["riot_neighbour"]) * CONTAGION[index], 4
    )
    return scenario


def _shortage(scenario: dict[str, Any], level: str, perspective: str) -> dict:
    factor = STOCK[STRESS_LEVELS.index(level)]
    for depot in _of(scenario, "depot"):
        depot["state"]["food"] = round(float(depot["state"]["food"]) * factor, 4)
    return scenario


def city_failure_variables() -> dict[str, FailureVariable]:
    """The variables a city reads in its own terms, by name."""
    return {
        "supply_delay": FailureVariable(
            "supply_delay",
            "Supplies arrive late: convoys take longer on every road",
            "supply",
            DELAY,
            _needs("convoy", "convoys"),
            _delay,
        ),
        "civilian_pressure": FailureVariable(
            "civilian_pressure",
            "Civilian pressure: public order starts lower in every district",
            "public_order",
            ORDER,
            _needs("district", "districts"),
            _pressure,
        ),
        "resource_shortage": FailureVariable(
            "resource_shortage",
            "Food runs short: the depots hold less, down to nothing",
            "supply",
            STOCK,
            _needs("depot", "depots"),
            _shortage,
        ),
        "public_order_collapse": FailureVariable(
            "public_order_collapse",
            "Public order collapses: districts recover slower and riots spread faster",
            "public_order",
            RECOVERY,
            _needs("district", "districts"),
            _collapse,
        ),
    }
