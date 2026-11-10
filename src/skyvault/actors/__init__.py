"""
Actors = who decides, kept outside the core (development plan Phase 6).

Important:
SKYVAULT decides only whether an action can happen, what it does, how it
is recorded and how it is judged. Everything here only proposes: a world
policy reads the world through a read-only view, and every other actor
turns an observation into an order. Nothing here imports the engine.
"""

from .view import EntityView, ReadOnlyWorldError, WorldView

__all__ = ["EntityView", "ReadOnlyWorldError", "WorldView"]
