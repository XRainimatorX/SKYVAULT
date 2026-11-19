"""
Actions = the one road from an actor's intent to a changed world.

Action Attempt → Validation → Resolution → Consequence → World Mutation →
Event Memory (Formal Spec section 6).

Important:
handlers only read the world and describe a Consequence; resolver applies it.
This package may use world_state, action, consequence, event_memory and
contracts. It never imports the engine, a policy or an exporter.
"""

from .handlers import CORE_HANDLERS, MILITARY_ACTION_TYPES, ActionHandler, handlers_for
from .resolver import ActionContext, ActionResolver, apply_consequence
from .validation import ActionValidation, action_cost, check_resources

__all__ = [
    "CORE_HANDLERS",
    "MILITARY_ACTION_TYPES",
    "ActionContext",
    "ActionHandler",
    "ActionResolver",
    "ActionValidation",
    "action_cost",
    "apply_consequence",
    "check_resources",
    "handlers_for",
]
