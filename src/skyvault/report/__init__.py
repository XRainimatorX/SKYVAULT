"""Report = the briefing built from a workspace, rendered as Markdown, DOCX or PDF."""

from .briefing import build_briefing
from .render import render_docx, render_markdown, render_pdf

__all__ = ["build_briefing", "render_docx", "render_markdown", "render_pdf"]
