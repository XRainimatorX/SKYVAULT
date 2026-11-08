"""Service = the UI backend: REST views, the replay WebSocket and the static UI."""

from .app import create_app

__all__ = ["create_app"]
