import asyncio
from uuid import UUID

import pytest
import pytest_asyncio

from app.models import JobStatus
from app.store import JobStore
from app.worker import JobWorkerPool


@pytest_asyncio.fixture
async def store():
    job_store = JobStore(max_queue_size=10)
    yield job_store


@pytest_asyncio.fixture
async def worker_pool(store):
    pool = JobWorkerPool(store, worker_count=1)
    await pool.start()
    yield pool
    await pool.stop()


async def wait_for_job_status(store: JobStore, job_id: UUID, expected: JobStatus, *, timeout: float = 2.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = await store.get(job_id)
        if job is not None and job.status == expected:
            return job
        await asyncio.sleep(0.02)
    job = await store.get(job_id)
    raise AssertionError(
        f"Timed out waiting for status {expected.value}; last status={getattr(job, 'status', None)}"
    )
