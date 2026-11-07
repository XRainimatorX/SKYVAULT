"""Entity contract = how one thing in the world is written down."""

from typing import Any

from pydantic import Field

from .base import ContractModel, NonEmptyStr, Position, check


class EntityRecord(ContractModel):
    """
    Entity = something that exists inside the world.

    Important:
    state holds what changes (hp, ap, status); capabilities holds what the
    entity can do (attack_damage, attack_range, accuracy). The contract keeps
    them as open mappings because their keys belong to the domain, not to core.
    """

    entity_id: NonEmptyStr
    name: str
    entity_type: str
    faction: str | None
    position: Position | None
    state: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


def validate_entity(data: dict[str, Any]) -> dict[str, Any]:
    """Validate one entity. Raises ContractError when it breaks the contract."""
    return check(EntityRecord, "entity", data)
