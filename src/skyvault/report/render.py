"""Briefing renderers: Markdown, DOCX and PDF, returned rather than written.

Important:
Each renderer takes the briefing dict and returns text or bytes; the caller
decides where they go. The same briefing always renders to the same bytes:
the PDF is written in reportlab's invariant mode, and the DOCX gets fixed
document properties and fixed timestamps inside its zip.
"""

import html
import io
import zipfile
from datetime import datetime
from typing import Any

from docx import Document
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    ListFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

AUTHOR = "SKYVAULT"


def escape(text: str) -> str:
    """Text safe inside reportlab's paragraph markup: only & < > matter."""
    return html.escape(text, quote=False)


def render_markdown(briefing: dict[str, Any]) -> str:
    """The briefing as Markdown."""
    lines = [f"# {briefing['title']}", ""]
    for part in briefing["sections"]:
        lines += [f"## {part['title']}", ""]
        for paragraph in part["paragraphs"]:
            lines += [paragraph, ""]
        if part["bullets"]:
            lines += [f"- {bullet}" for bullet in part["bullets"]] + [""]
        table = part["table"]
        if table:
            lines.append("| " + " | ".join(table["columns"]) + " |")
            lines.append("|" + "---|" * len(table["columns"]))
            lines += ["| " + " | ".join(row) + " |" for row in table["rows"]]
            lines.append("")
    return "\n".join(lines)


def render_docx(briefing: dict[str, Any], created: datetime | None = None) -> bytes:
    """
    The briefing as a Word document.

    created defaults to the briefing's own (the run's end time); it is the
    document's creation and modification date and the zip entries' time.
    """
    when = created or datetime.fromisoformat(briefing["created"])
    when = when.replace(tzinfo=None, microsecond=0)
    document = Document()
    properties = document.core_properties
    properties.title = briefing["title"]
    properties.author = AUTHOR
    properties.last_modified_by = AUTHOR
    properties.created = when
    properties.modified = when
    properties.revision = 1

    document.add_heading(briefing["title"], level=0)
    for part in briefing["sections"]:
        document.add_heading(part["title"], level=1)
        for paragraph in part["paragraphs"]:
            document.add_paragraph(paragraph)
        for bullet in part["bullets"]:
            document.add_paragraph(bullet, style="List Bullet")
        table = part["table"]
        if table:
            grid = document.add_table(rows=1, cols=len(table["columns"]))
            grid.style = "Table Grid"
            for cell, column in zip(grid.rows[0].cells, table["columns"], strict=True):
                cell.text = column
            for row in table["rows"]:
                for cell, value in zip(grid.add_row().cells, row, strict=True):
                    cell.text = value

    buffer = io.BytesIO()
    document.save(buffer)
    return _fix_zip_times(buffer.getvalue(), when)


def render_pdf(briefing: dict[str, Any]) -> bytes:
    """The briefing as an A4 PDF."""
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=briefing["title"],
        author=AUTHOR,
        invariant=1,
    )
    story: list[Any] = [Paragraph(escape(briefing["title"]), styles["Title"])]
    for part in briefing["sections"]:
        story.append(Paragraph(escape(part["title"]), styles["Heading2"]))
        for paragraph in part["paragraphs"]:
            story.append(Paragraph(escape(paragraph), styles["BodyText"]))
        if part["bullets"]:
            story.append(
                ListFlowable(
                    [
                        Paragraph(escape(bullet), styles["BodyText"])
                        for bullet in part["bullets"]
                    ],
                    bulletType="bullet",
                )
            )
        table = part["table"]
        if table:
            grid = Table([table["columns"], *table["rows"]], repeatRows=1)
            grid.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story += [Spacer(1, 6), grid]
        story.append(Spacer(1, 8))
    document.build(story)
    return buffer.getvalue()


def _fix_zip_times(data: bytes, when: datetime) -> bytes:
    """The same zip with every entry stamped with when, in the same order."""
    stamp = (max(when.year, 1980), when.month, when.day, when.hour, when.minute, 0)
    source = zipfile.ZipFile(io.BytesIO(data))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=stamp)
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            target.writestr(fixed, source.read(info.filename))
    return buffer.getvalue()
