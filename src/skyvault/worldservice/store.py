"""Store = where the world service keeps its jobs, results and checkpoints.

Important:
One schema, two databases: SQLite (the standard library; the default, a
file or memory) and PostgreSQL (psycopg). The SQL is written once, with ?
placeholders that the PostgreSQL store turns into %s. Records are JSON
text: the service reads them back exactly as it wrote them. A store is
named by a spec string, so a worker in another process opens the same one:
"sqlite:///relative/file", "sqlite:////absolute/file" (four slashes, as in
SQLAlchemy), "sqlite://" (memory) or "postgresql://...".
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, kind TEXT NOT NULL,
        lifecycle_state TEXT NOT NULL, record TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS results (
        job_id TEXT PRIMARY KEY, package TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS checkpoints (
        world_id TEXT NOT NULL, n INTEGER NOT NULL, checkpoint TEXT NOT NULL,
        PRIMARY KEY (world_id, n))""",
    """CREATE TABLE IF NOT EXISTS job_events (
        job_id TEXT NOT NULL, n INTEGER NOT NULL, at TEXT NOT NULL,
        message TEXT NOT NULL, PRIMARY KEY (job_id, n))""",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore(Protocol):
    spec: str

    def next_job_id(self) -> str: ...
    def create_job(self, job: dict[str, Any]) -> None: ...
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any]: ...
    def list_jobs(self) -> list[dict[str, Any]]: ...
    def save_result(self, job_id: str, package: dict[str, Any]) -> None: ...
    def get_result(self, job_id: str) -> dict[str, Any] | None: ...
    def add_checkpoint(self, world_id: str, checkpoint: dict[str, Any]) -> int: ...
    def checkpoints(self, world_id: str) -> list[dict[str, Any]]: ...
    def log(self, job_id: str, message: str) -> None: ...
    def events(self, job_id: str) -> list[dict[str, Any]]: ...


class _SQLStore:
    """Everything both databases share; subclasses only connect."""

    spec = ""
    placeholder = "?"

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        raise NotImplementedError  # pragma: no cover - every store connects

    def _sql(self, sql: str) -> str:
        return sql.replace("?", self.placeholder)

    def setup(self) -> None:
        for statement in SCHEMA:
            self._run(statement)

    def next_job_id(self) -> str:
        rows = self._run("SELECT COALESCE(MAX(seq), 0) FROM jobs")
        return f"job_{int(rows[0][0]) + 1:06d}"

    def create_job(self, job: dict[str, Any]) -> None:
        seq = int(job["job_id"].split("_")[-1])
        self._run(
            "INSERT INTO jobs (job_id, seq, kind, lifecycle_state, record) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                job["job_id"],
                seq,
                job["request"]["kind"],
                job["lifecycle_state"],
                json.dumps(job, sort_keys=True),
            ),
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        rows = self._run("SELECT record FROM jobs WHERE job_id = ?", (job_id,))
        if not rows:
            raise KeyError(f"no job {job_id}")
        job: dict[str, Any] = json.loads(rows[0][0])
        return job

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any]:
        job = self.get_job(job_id)
        job.update(fields)
        job["updated_at"] = now()
        self._run(
            "UPDATE jobs SET lifecycle_state = ?, record = ? WHERE job_id = ?",
            (job["lifecycle_state"], json.dumps(job, sort_keys=True), job_id),
        )
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        rows = self._run("SELECT record FROM jobs ORDER BY seq")
        return [json.loads(row[0]) for row in rows]

    def save_result(self, job_id: str, package: dict[str, Any]) -> None:
        self._run(
            "INSERT INTO results (job_id, package) VALUES (?, ?) "
            "ON CONFLICT (job_id) DO UPDATE SET package = excluded.package",
            (job_id, json.dumps(package, sort_keys=True)),
        )

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        rows = self._run("SELECT package FROM results WHERE job_id = ?", (job_id,))
        if not rows:
            return None
        package: dict[str, Any] = json.loads(rows[0][0])
        return package

    def add_checkpoint(self, world_id: str, checkpoint: dict[str, Any]) -> int:
        rows = self._run(
            "SELECT COALESCE(MAX(n), 0) FROM checkpoints WHERE world_id = ?",
            (world_id,),
        )
        n = int(rows[0][0]) + 1
        self._run(
            "INSERT INTO checkpoints (world_id, n, checkpoint) VALUES (?, ?, ?)",
            (world_id, n, json.dumps(checkpoint, sort_keys=True)),
        )
        return n

    def checkpoints(self, world_id: str) -> list[dict[str, Any]]:
        rows = self._run(
            "SELECT checkpoint FROM checkpoints WHERE world_id = ? ORDER BY n",
            (world_id,),
        )
        return [json.loads(row[0]) for row in rows]

    def log(self, job_id: str, message: str) -> None:
        rows = self._run(
            "SELECT COALESCE(MAX(n), 0) FROM job_events WHERE job_id = ?", (job_id,)
        )
        self._run(
            "INSERT INTO job_events (job_id, n, at, message) VALUES (?, ?, ?, ?)",
            (job_id, int(rows[0][0]) + 1, now(), message),
        )

    def events(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._run(
            "SELECT n, at, message FROM job_events WHERE job_id = ? ORDER BY n",
            (job_id,),
        )
        return [{"n": int(n), "at": at, "message": message} for n, at, message in rows]


class SQLiteStore(_SQLStore):
    """SQLite: one connection, shared by the service's threads under a lock."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self.spec = "sqlite://" if path == ":memory:" else f"sqlite:///{path}"
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self.setup()

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            cursor = self._db.execute(self._sql(sql), params)
            rows = cursor.fetchall()
            self._db.commit()
            return rows


class PostgresStore(_SQLStore):
    """PostgreSQL through psycopg: a connection per statement, safe from any thread."""

    placeholder = "%s"

    def __init__(self, dsn: str) -> None:
        import psycopg

        self.spec = dsn
        self._connect = lambda: psycopg.connect(dsn, autocommit=True)
        self.setup()

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._sql(sql), params)
            return list(cursor.fetchall()) if cursor.description else []


def open_store(spec: str) -> JobStore:
    """The store a spec string names (sqlite:///file, sqlite://, postgresql://...)."""
    if spec == "sqlite://":
        return SQLiteStore()
    if spec.startswith("sqlite:///"):
        return SQLiteStore(spec[len("sqlite:///") :])
    if spec.startswith(("postgresql://", "postgres://")):
        return PostgresStore(spec)
    raise ValueError(
        f"unknown store {spec!r}: use sqlite:///file, sqlite:// or postgresql://"
    )
