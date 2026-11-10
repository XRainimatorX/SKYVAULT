"""Store = where the world service keeps its jobs, results and checkpoints.

Important:
One schema, two databases: SQLite (the standard library; the default, a
file or memory) and PostgreSQL (psycopg). The SQL is written once, with ?
placeholders that the PostgreSQL store turns into %s. Records are JSON
text: the service reads them back exactly as it wrote them. A store is
named by a spec string, so a worker in another process opens the same one:
"sqlite:///relative/file", "sqlite:////absolute/file" (four slashes, as in
SQLAlchemy), "sqlite://" (memory) or "postgresql://...".

Every read-modify-write runs in one transaction (a worker and a cancel
request may write the same job at once), and every numbered record —
jobs included — takes its number in the insert that claims it.
"""

import json
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
    """CREATE TABLE IF NOT EXISTS conflicts (
        conflict_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, record TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS job_events (
        job_id TEXT NOT NULL, n INTEGER NOT NULL, at TEXT NOT NULL,
        message TEXT NOT NULL, PRIMARY KEY (job_id, n))""",
)
# a numbered insert that keeps losing the race gives up after this many tries
ATTEMPTS = 50


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore(Protocol):
    spec: str

    def create_job(self, job: dict[str, Any]) -> dict[str, Any]: ...
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def update_job(
        self,
        job_id: str,
        summary_fields: dict[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]: ...
    def merge_summary(self, job_id: str, **fields: Any) -> dict[str, Any]: ...
    def list_jobs(self) -> list[dict[str, Any]]: ...
    def save_result(self, job_id: str, package: dict[str, Any]) -> None: ...
    def get_result(self, job_id: str) -> dict[str, Any] | None: ...
    def add_checkpoint(self, world_id: str, checkpoint: dict[str, Any]) -> int: ...
    def checkpoints(self, world_id: str) -> list[dict[str, Any]]: ...
    def log(self, job_id: str, message: str) -> None: ...
    def save_conflict(self, record: dict[str, Any]) -> dict[str, Any]: ...
    def get_conflict(self, conflict_id: str) -> dict[str, Any]: ...
    def update_conflict(self, conflict_id: str, **fields: Any) -> dict[str, Any]: ...
    def events(self, job_id: str) -> list[dict[str, Any]]: ...


class _SQLStore:
    """Everything both databases share; subclasses only connect."""

    spec = ""
    placeholder = "?"
    # the SELECTs a read-modify-write reads (and, where the database can,
    # locks) its row with
    select_job_to_change = "SELECT record FROM jobs WHERE job_id = ?"
    select_conflict_to_change = "SELECT record FROM conflicts WHERE conflict_id = ?"

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        raise NotImplementedError  # pragma: no cover - every store connects

    @contextmanager
    def _transaction(self) -> Iterator[Callable[..., list[tuple[Any, ...]]]]:
        raise NotImplementedError  # pragma: no cover - every store connects
        yield  # pragma: no cover

    def _sql(self, sql: str) -> str:
        return sql.replace("?", self.placeholder)

    def setup(self) -> None:
        for statement in SCHEMA:
            self._run(statement)

    def _is_duplicate(self, error: Exception) -> bool:
        return isinstance(error, sqlite3.IntegrityError)

    def _insert_next(
        self,
        select: str,
        select_params: tuple[Any, ...],
        insert: str,
        params: Callable[[int], tuple[Any, ...]],
    ) -> int:
        """
        Insert the record numbered one past the highest so far; return its
        number. Two writers can read the same highest number (a worker and a
        stop request logging at once): the second insert then hits the
        primary key and is retried with a fresh number.
        """
        for attempt in range(ATTEMPTS):
            n = int(self._run(select, select_params)[0][0]) + 1
            try:
                self._run(insert, params(n))
                return n
            except Exception as error:
                if attempt == ATTEMPTS - 1 or not self._is_duplicate(error):
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    def create_job(self, job: dict[str, Any]) -> dict[str, Any]:
        """Keep a new job as job_<next n>; return it with that id."""

        def row(seq: int) -> tuple[Any, ...]:
            saved = {**job, "job_id": f"job_{seq:06d}"}
            return (
                saved["job_id"],
                seq,
                saved["request"]["kind"],
                saved["lifecycle_state"],
                json.dumps(saved, sort_keys=True),
            )

        seq = self._insert_next(
            "SELECT COALESCE(MAX(seq), 0) FROM jobs",
            (),
            "INSERT INTO jobs (job_id, seq, kind, lifecycle_state, record) "
            "VALUES (?, ?, ?, ?, ?)",
            row,
        )
        return {**job, "job_id": f"job_{seq:06d}"}

    def get_job(self, job_id: str) -> dict[str, Any]:
        rows = self._run("SELECT record FROM jobs WHERE job_id = ?", (job_id,))
        if not rows:
            raise KeyError(f"no job {job_id}")
        job: dict[str, Any] = json.loads(rows[0][0])
        return job

    def _modify_job(
        self, job_id: str, change: Callable[[dict[str, Any]], None]
    ) -> dict[str, Any]:
        """Read, change and write one job in a single transaction."""
        with self._transaction() as run:
            rows = run(self.select_job_to_change, (job_id,))
            if not rows:
                raise KeyError(f"no job {job_id}")
            job: dict[str, Any] = json.loads(rows[0][0])
            change(job)
            job["updated_at"] = now()
            run(
                "UPDATE jobs SET lifecycle_state = ?, record = ? WHERE job_id = ?",
                (job["lifecycle_state"], json.dumps(job, sort_keys=True), job_id),
            )
            return job

    def update_job(
        self,
        job_id: str,
        summary_fields: dict[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """
        Set fields of the job; summary_fields are added to its summary as it
        stands when written (never to a copy read earlier).
        """

        def change(job: dict[str, Any]) -> None:
            job.update(fields)
            if summary_fields:
                job["summary"] = {**job["summary"], **summary_fields}

        return self._modify_job(job_id, change)

    def merge_summary(self, job_id: str, **fields: Any) -> dict[str, Any]:
        """Add fields to the job's summary, keeping whatever else is there."""
        return self.update_job(job_id, summary_fields=fields)

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
        return self._insert_next(
            "SELECT COALESCE(MAX(n), 0) FROM checkpoints WHERE world_id = ?",
            (world_id,),
            "INSERT INTO checkpoints (world_id, n, checkpoint) VALUES (?, ?, ?)",
            lambda n: (world_id, n, json.dumps(checkpoint, sort_keys=True)),
        )

    def checkpoints(self, world_id: str) -> list[dict[str, Any]]:
        rows = self._run(
            "SELECT checkpoint FROM checkpoints WHERE world_id = ? ORDER BY n",
            (world_id,),
        )
        return [json.loads(row[0]) for row in rows]

    def save_conflict(self, record: dict[str, Any]) -> dict[str, Any]:
        """Keep a new conflict as conflict_<next n>; return it with that id."""

        def row(seq: int) -> tuple[Any, ...]:
            saved = {**record, "conflict_id": f"conflict_{seq:06d}"}
            return (saved["conflict_id"], seq, json.dumps(saved, sort_keys=True))

        seq = self._insert_next(
            "SELECT COALESCE(MAX(seq), 0) FROM conflicts",
            (),
            "INSERT INTO conflicts (conflict_id, seq, record) VALUES (?, ?, ?)",
            row,
        )
        return {**record, "conflict_id": f"conflict_{seq:06d}"}

    def get_conflict(self, conflict_id: str) -> dict[str, Any]:
        rows = self._run(
            "SELECT record FROM conflicts WHERE conflict_id = ?", (conflict_id,)
        )
        if not rows:
            raise KeyError(f"no conflict {conflict_id}")
        record: dict[str, Any] = json.loads(rows[0][0])
        return record

    def update_conflict(self, conflict_id: str, **fields: Any) -> dict[str, Any]:
        with self._transaction() as run:
            rows = run(self.select_conflict_to_change, (conflict_id,))
            if not rows:
                raise KeyError(f"no conflict {conflict_id}")
            record: dict[str, Any] = {**json.loads(rows[0][0]), **fields}
            run(
                "UPDATE conflicts SET record = ? WHERE conflict_id = ?",
                (json.dumps(record, sort_keys=True), conflict_id),
            )
            return record

    def log(self, job_id: str, message: str) -> None:
        self._insert_next(
            "SELECT COALESCE(MAX(n), 0) FROM job_events WHERE job_id = ?",
            (job_id,),
            "INSERT INTO job_events (job_id, n, at, message) VALUES (?, ?, ?, ?)",
            lambda n: (job_id, n, now(), message),
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
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self.setup()

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._transaction() as run:
            return run(sql, params)

    @contextmanager
    def _transaction(self) -> Iterator[Callable[..., list[tuple[Any, ...]]]]:
        """The one connection, held for the whole transaction."""

        def run(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
            return self._db.execute(self._sql(sql), params).fetchall()

        with self._lock:
            try:
                yield run
            except BaseException:
                self._db.rollback()
                raise
            self._db.commit()


class PostgresStore(_SQLStore):
    """PostgreSQL through psycopg: a connection per statement, safe from any thread."""

    placeholder = "%s"
    select_job_to_change = "SELECT record FROM jobs WHERE job_id = ? FOR UPDATE"
    select_conflict_to_change = (
        "SELECT record FROM conflicts WHERE conflict_id = ? FOR UPDATE"
    )

    def __init__(self, dsn: str) -> None:
        import psycopg

        self.spec = dsn
        self._connect = lambda: psycopg.connect(dsn, autocommit=True)
        self.setup()

    def _is_duplicate(self, error: Exception) -> bool:
        import psycopg

        return isinstance(error, psycopg.errors.UniqueViolation)

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._sql(sql), params)
            return list(cursor.fetchall()) if cursor.description else []

    @contextmanager
    def _transaction(self) -> Iterator[Callable[..., list[tuple[Any, ...]]]]:
        """One connection and one transaction; FOR UPDATE locks the row read."""
        with (
            self._connect() as connection,
            connection.transaction(),
            connection.cursor() as cursor,
        ):

            def run(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
                cursor.execute(self._sql(sql), params)
                return list(cursor.fetchall()) if cursor.description else []

            yield run


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
