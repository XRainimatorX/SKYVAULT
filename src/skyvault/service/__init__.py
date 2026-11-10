"""Service = the UI's routes: a run's screens, its replay and the static UI."""

from .app import NoSuchRun, add_view_routes, mount_ui

__all__ = ["NoSuchRun", "add_view_routes", "mount_ui"]
