"""Queues = where admitted jobs wait for a worker, in order of priority.

Important:
Two queues with one interface. InProcessQueue runs jobs on threads of the
service's own process — for a single machine, for tests, and when there
is no Redis. RQQueue puts them on Redis for RQ workers in other processes
(scripts/world_worker.py); a worker opens the same store from its spec
string. Either way at most max_parallel_runs jobs run at once and, under
priority_then_fifo, a higher priority always goes first, equal ones in the
order they came. Cancelling a waiting job takes it out of the queue; a
running job is cancelled through the store, which its governor reads.
"""

import heapq
import itertools
import math
import threading
from collections.abc import Callable
from typing import Any, Protocol

from .governance import load_governance
from .jobs import execute_job
from .store import open_store

RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}


class JobQueue(Protocol):
    def submit(self, job_id: str, priority: str) -> None: ...
    def cancel(self, job_id: str) -> bool: ...
    def depth(self) -> int: ...
    def running(self) -> list[str]: ...


class InProcessQueue:
    """Jobs on this process's threads, max_parallel_runs at a time."""

    def __init__(
        self,
        executor: Callable[[str], None],
        max_parallel_runs: int = 1,
        queue_policy: str = "priority_then_fifo",
        start: bool = True,
    ) -> None:
        self.executor = executor
        self.max_parallel_runs = max_parallel_runs
        self.queue_policy = queue_policy
        self._heap: list[tuple[int, int, str]] = []
        self._order = itertools.count()
        self._running: set[str] = set()
        self._ready = threading.Condition()
        self._threads: list[threading.Thread] = []
        self._closing = False
        if start:
            self.start()

    def start(self) -> None:
        """Start the workers (once)."""
        with self._ready:
            if self._threads:
                return
            for n in range(self.max_parallel_runs):
                thread = threading.Thread(
                    target=self._work, name=f"world-worker-{n}", daemon=True
                )
                self._threads.append(thread)
                thread.start()

    def submit(self, job_id: str, priority: str) -> None:
        rank = RANK[priority] if self.queue_policy == "priority_then_fifo" else 0
        with self._ready:
            heapq.heappush(self._heap, (rank, next(self._order), job_id))
            self._ready.notify_all()

    def cancel(self, job_id: str) -> bool:
        """Take a waiting job out of the queue; False if it is not waiting."""
        with self._ready:
            for entry in self._heap:
                if entry[2] == job_id:
                    self._heap.remove(entry)
                    heapq.heapify(self._heap)
                    return True
        return False

    def depth(self) -> int:
        with self._ready:
            return len(self._heap)

    def running(self) -> list[str]:
        with self._ready:
            return sorted(self._running)

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Wait until nothing waits and nothing runs; False on timeout."""
        with self._ready:
            return self._ready.wait_for(
                lambda: not self._heap and not self._running, timeout
            )

    def close(self) -> None:
        """Stop the workers once they finish what they are running."""
        with self._ready:
            self._closing = True
            self._ready.notify_all()
        for thread in self._threads:
            thread.join(timeout=30)

    def _work(self) -> None:
        while True:
            with self._ready:
                self._ready.wait_for(lambda: self._heap or self._closing)
                if self._closing:
                    return
                _, _, job_id = heapq.heappop(self._heap)
                self._running.add(job_id)
            try:
                self.executor(job_id)
            finally:
                with self._ready:
                    self._running.discard(job_id)
                    self._ready.notify_all()


def run_queued(job_id: str, store_spec: str, governance: str = "governance") -> None:
    """What an RQ worker runs: open the store and the policy, execute the job."""
    execute_job(job_id, open_store(store_spec), load_governance(governance))


class RQQueue:
    """
    Jobs on Redis for RQ workers: one RQ queue per priority, and workers that
    always empty the higher one first.

    Important:
    RQ itself also stops a job that outlives twice max_runtime_seconds — a
    second line behind the governor, for a worker that hangs outside a tick.
    """

    def __init__(
        self,
        redis_url: str,
        store_spec: str,
        governance: str = "governance",
        policy: dict[str, Any] | None = None,
    ) -> None:
        import redis
        import rq

        self.connection = redis.Redis.from_url(redis_url)
        self.store_spec = store_spec
        self.governance = governance
        self.policy = policy or load_governance(governance)
        names = (
            list(RANK)
            if self.policy["queue_policy"] == "priority_then_fifo"
            else ["normal"]
        )
        self.queues = {
            name: rq.Queue(f"skyvault-{name}", connection=self.connection)
            for name in names
        }
        seconds = self.policy["max_runtime_seconds"]
        self.job_timeout = None if seconds is None else math.ceil(seconds * 2)

    def _queue(self, priority: str) -> Any:
        return self.queues.get(priority) or self.queues["normal"]

    def submit(self, job_id: str, priority: str) -> None:
        self._queue(priority).enqueue(
            run_queued,
            job_id,
            self.store_spec,
            self.governance,
            job_id=job_id,
            job_timeout=self.job_timeout,
        )

    def cancel(self, job_id: str) -> bool:
        from rq.job import Job, JobStatus

        try:
            job = Job.fetch(job_id, connection=self.connection)
        except Exception:  # no such job on Redis
            return False
        if job.get_status() != JobStatus.QUEUED:
            return False
        job.cancel()
        return True

    def depth(self) -> int:
        return sum(len(queue) for queue in self.queues.values())

    def running(self) -> list[str]:
        return sorted(
            job_id
            for queue in self.queues.values()
            for job_id in queue.started_job_registry.get_job_ids()
        )

    def worker(self, burst: bool = False) -> Any:
        """An RQ worker over the queues, highest priority first."""
        import rq

        kind = rq.SimpleWorker if burst else rq.Worker
        ordered = [self.queues[name] for name in RANK if name in self.queues]
        return kind(ordered, connection=self.connection)

    def clear(self) -> None:
        """Empty every queue (tests and operators)."""
        for queue in self.queues.values():
            queue.empty()
