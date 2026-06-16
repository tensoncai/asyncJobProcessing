from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from app.jobs.errors import QueueFullError
from app.models import JobStatus

DEFAULT_MAX_QUEUE_SIZE = 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    id: UUID
    payload: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    result: Optional[Any] = None
    error: Optional[str] = None
    attempts: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=_utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobStore:
    """In-memory job store and async queue."""

    def __init__(self, max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE) -> None:
        self._max_queue_size = max_queue_size
        self._jobs: dict[UUID, Job] = {}
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[UUID] = asyncio.Queue(maxsize=max_queue_size)

    @property
    def max_queue_size(self) -> int:
        return self._max_queue_size

    def queue_size(self) -> int:
        return self._queue.qsize()

    async def create(self, payload: dict[str, Any], *, max_retries: int) -> Job:
        if self._queue.full():
            raise QueueFullError(
                f"Job queue is full (max {self._max_queue_size} pending jobs)"
            )

        job = Job(id=uuid4(), payload=payload, max_retries=max_retries)
        async with self._lock:
            self._jobs[job.id] = job

        try:
            self._queue.put_nowait(job.id)
        except asyncio.QueueFull:
            async with self._lock:
                del self._jobs[job.id]
            raise QueueFullError(
                f"Job queue is full (max {self._max_queue_size} pending jobs)"
            ) from None

        return job

    async def get(self, job_id: UUID) -> Optional[Job]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return Job(
                id=job.id,
                payload=dict(job.payload),
                status=job.status,
                result=job.result,
                error=job.error,
                attempts=job.attempts,
                max_retries=job.max_retries,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
            )

    async def dequeue(self) -> UUID:
        return await self._queue.get()

    async def mark_running(self, job_id: UUID) -> Optional[Job]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.QUEUED:
                return None
            job.attempts += 1
            job.status = JobStatus.RUNNING
            job.error = None
            if job.started_at is None:
                job.started_at = _utcnow()
            return job

    async def _enqueue(self, job_id: UUID) -> None:
        try:
            self._queue.put_nowait(job_id)
        except asyncio.QueueFull as exc:
            raise QueueFullError(
                f"Job queue is full (max {self._max_queue_size} pending jobs)"
            ) from exc

    async def requeue(self, job_id: UUID, error: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.RUNNING:
                return False
            job.status = JobStatus.QUEUED
            job.error = error

        try:
            await self._enqueue(job_id)
        except QueueFullError:
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.status = JobStatus.RUNNING
            return False

        return True

    async def mark_completed(self, job_id: UUID, result: Any) -> Optional[Job]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = JobStatus.COMPLETED
            job.result = result
            job.error = None
            job.completed_at = _utcnow()
            return job

    async def mark_failed(self, job_id: UUID, error: str) -> Optional[Job]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                return job
            job.status = JobStatus.FAILED
            job.error = error
            job.completed_at = _utcnow()
            return job

    def task_done(self) -> None:
        self._queue.task_done()

    def reset_for_tests(self, max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE) -> None:
        """Clear all jobs and pending queue items (test helper)."""
        self._max_queue_size = max_queue_size
        self._jobs.clear()
        self._queue = asyncio.Queue(maxsize=max_queue_size)


job_store = JobStore()
