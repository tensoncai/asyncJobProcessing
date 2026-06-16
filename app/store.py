from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from app.models import JobStatus


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

    def __init__(self) -> None:
        self._jobs: dict[UUID, Job] = {}
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()

    async def create(self, payload: dict[str, Any], *, max_retries: int) -> Job:
        job = Job(id=uuid4(), payload=payload, max_retries=max_retries)
        async with self._lock:
            self._jobs[job.id] = job
        await self._queue.put(job.id)
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

    async def requeue(self, job_id: UUID, error: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.RUNNING:
                return False
            job.status = JobStatus.QUEUED
            job.error = error
        await self._queue.put(job_id)
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

    def reset_for_tests(self) -> None:
        """Clear all jobs and pending queue items (test helper)."""
        self._jobs.clear()
        self._queue = asyncio.Queue()


job_store = JobStore()
