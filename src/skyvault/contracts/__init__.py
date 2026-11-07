"""
Contracts = the formal shapes every piece of SKYVAULT data must keep.

Each contract is a Pydantic model plus one pure validate_<name>() function.
A validator returns the data as plain JSON-safe dicts when it passes and raises
ContractError, listing every violation, when it does not.

Important:
This package imports nothing else from skyvault. Contracts sit below every
other module, so any module may depend on them and they depend on none.
"""

from .action import ActionRecord, validate_action
from .base import SCHEMA_VERSION
from .consequence import ConsequenceRecord, validate_consequence
from .entity import EntityRecord, validate_entity
from .errors import ContractError
from .event import EVENT_TYPES, EventRecord, validate_event

__all__ = [
    "SCHEMA_VERSION",
    "ContractError",
    "EVENT_TYPES",
    "ActionRecord",
    "ConsequenceRecord",
    "EntityRecord",
    "EventRecord",
    "validate_action",
    "validate_consequence",
    "validate_entity",
    "validate_event",
]
