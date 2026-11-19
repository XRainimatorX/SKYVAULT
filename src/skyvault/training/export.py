"""Writing datasets: JSON Lines and Parquet, the same rows in both.

Important:
JSON Lines are written with sorted keys, one record per line, in the given
order. Parquet stores each top-level field as a column; nested values are
stored as JSON text so any schema of record round-trips exactly.
read_parquet returns the records as they were given.
"""

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


def to_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_jsonl(rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    """rows as a Parquet table: one column per field, nested fields as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = sorted({key for row in rows for key in row})
    table = pa.table(
        {
            key: pa.array(
                [
                    (
                        json.dumps(row[key], ensure_ascii=False, sort_keys=True)
                        if key in row
                        else None
                    )
                    for row in rows
                ],
                type=pa.string(),
            )
            for key in columns
        }
    )
    pq.write_table(table, path)


def read_parquet(path: Path) -> list[dict[str, Any]]:
    table = pq.read_table(path).to_pydict()
    count = len(next(iter(table.values()), []))
    return [
        {
            key: json.loads(values[i])
            for key, values in table.items()
            if values[i] is not None
        }
        for i in range(count)
    ]
