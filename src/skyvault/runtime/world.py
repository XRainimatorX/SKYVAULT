"""create_world = turn a validated scenario into a running world instance."""

from typing import Any

from ..entity import Entity
from ..world_state import WorldState
from .clock import build_clock
from .registry import EntityRegistry
from .resources import ResourceState
from .rules import RuleSet
from .space import build_space


def entity_from_record(record: dict[str, Any]) -> Entity:
    """
    One entity from its contract record.

    Important:
    A grid position arrives as a JSON list and becomes a tuple, which is what
    the space and the policy compare against. A graph position is a node id
    and stays a string.
    """
    position = record.get("position")

    if isinstance(position, list):
        position = tuple(position)

    return Entity(
        entity_id=record["entity_id"],
        name=record["name"],
        entity_type=record["entity_type"],
        faction=record.get("faction"),
        position=position,
        state=dict(record.get("state", {})),
        capabilities=dict(record.get("capabilities", {})),
        tags=list(record.get("tags", [])),
    )


def create_world(scenario: dict[str, Any]) -> WorldState:
    """
    The time-zero world a scenario describes.

    Important:
    Space, clock, resources and rules all come from the world contract, so
    the same function builds a grid, graph or network world on any kind of
    clock. Nothing here knows about tactics.

    The scenario is expected to have passed validate_scenario. An entity
    placed outside the space is still refused here, because only the built
    space can answer whether a position exists in it.
    """
    world_contract = scenario["world_contract"]
    space = build_space(world_contract["space_model"])
    entities = EntityRegistry(entity_from_record(item) for item in scenario["entities"])

    for entity in entities.values():
        if entity.position is not None and not space.is_inside(entity.position):
            raise ValueError(
                f"entity {entity.entity_id!r} is placed at {entity.position!r}, "
                "outside the world's space"
            )

    return WorldState(
        world_id=world_contract["world_id"],
        scenario_id=scenario["scenario_id"],
        tick=0,
        space=space,
        entities=entities,
        assumptions=dict(world_contract.get("assumption_registry", {})),
        resources=ResourceState(world_contract.get("resource_state", {})),
        rules=RuleSet(world_contract.get("rule_set", {})),
        clock=build_clock(world_contract["time_model"]),
        environment=dict(world_contract.get("environment_state", {})),
    )
