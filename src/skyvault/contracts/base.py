"""Shared machinery for every contract: one base model and one validation path."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ContractError

SCHEMA_VERSION = "0.3"

NonEmptyStr = Annotated[str, Field(min_length=1)]
Position = Annotated[list[int], Field(min_length=2, max_length=2)]
# A grid cell, or a node id on a graph or network space.
Location = Position | NonEmptyStr
NonNegative = Annotated[float, Field(ge=0.0)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ContractModel(BaseModel):
    """
    Base for every contract model.

    Important:
    Unknown keys are rejected. A contract is a law about shape, so a misspelt
    field must fail loudly instead of being silently ignored.
    """

    model_config = ConfigDict(extra="forbid")


def check(model: type[ContractModel], contract: str, data: Any) -> dict[str, Any]:
    """
    Validate data against a contract model and return it as plain JSON-safe data.

    Important:
    Only fields the caller actually supplied come back. Optional fields left out
    of the input are not filled in, so validating data never changes its shape.
    """
    try:
        instance = model.model_validate(data)
    except ValidationError as error:
        raise ContractError(
            contract,
            [_describe(item) for item in error.errors()],
        ) from None

    return instance.model_dump(mode="json", exclude_unset=True)


def _describe(item: Any) -> str:
    """One violation as "<field path>: <message>"."""
    path = ".".join(str(part) for part in item["loc"]) or "<root>"
    return f"{path}: {item['msg']}"
