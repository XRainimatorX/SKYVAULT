"""redact = the internal names an edition must not show, replaced by its aliases.

Important:
Pure. Applied only at an edition's edge (its responses and product
outputs), never to the core's code or data. A name is matched whole, in any
letter case and with spaces, underscores or hyphens between its words
("TAC ANGEL", "tac_angel", "Tac-Angel"). The alias keeps the match's style:
a lower-case match (an identifier such as tac_angel_adapter) gets the
snake_case alias (tactical_agent_adapter), anything else the alias as
written ("Tactical Agent"). Dictionary keys are redacted the same way;
numbers, booleans and the shape of the data never change.

An edition with no redaction table returns its data unchanged.
"""

import json
import re
from typing import Any


def _pattern(name: str) -> str:
    words = [re.escape(w) for w in re.split(r"[ _\-]+", name) if w]
    return r"[ _\-]?".join(words)


def _compiled(table: dict[str, str]) -> re.Pattern[str] | None:
    if not table:
        return None
    names = sorted(table, key=len, reverse=True)
    body = "|".join(f"({_pattern(n)})" for n in names)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.IGNORECASE)


def _snake(alias: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")


def _replacer(table: dict[str, str]) -> Any:
    names = sorted(table, key=len, reverse=True)

    def replace(match: re.Match[str]) -> str:
        index = next(i for i, group in enumerate(match.groups()) if group is not None)
        alias = table[names[index]]
        text = match.group(0)
        return _snake(alias) if text == text.lower() and text.isascii() else alias

    return replace


def redact_text(text: str, edition: dict[str, Any]) -> str:
    table = edition.get("redact") or {}
    pattern = _compiled(table)
    return text if pattern is None else pattern.sub(_replacer(table), text)


def redact(data: Any, edition: dict[str, Any]) -> Any:
    """data with every internal name replaced by its alias (keys included)."""
    if not edition.get("redact"):
        return data
    if isinstance(data, str):
        return redact_text(data, edition)
    if isinstance(data, list):
        return [redact(item, edition) for item in data]
    if isinstance(data, tuple):
        return tuple(redact(item, edition) for item in data)
    if isinstance(data, dict):
        return {
            (redact_text(k, edition) if isinstance(k, str) else k): redact(v, edition)
            for k, v in data.items()
        }
    return data


def leaks(data: Any, edition: dict[str, Any]) -> list[str]:
    """The internal names still present anywhere in data, as written there."""
    table = edition.get("redact") or {}
    pattern = _compiled(table)
    if pattern is None:
        return []
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return sorted({m.group(0) for m in pattern.finditer(text)})
