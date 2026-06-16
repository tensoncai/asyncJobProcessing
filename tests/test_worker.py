from unittest.mock import AsyncMock, patch

import pytest

from app.jobs.errors import TransientError
from app.models import JobStatus
from tests.conftest import wait_for_job_status


@pytest.mark.asyncio
@patch("app.worker.process_job", new_callable=AsyncMock)
async def test_worker_marks_job_completed_on_success(mock_process_job, store, worker_pool):
    mock_process_job.return_value = {
        "slept_seconds": 0,
        "message": "Job completed successfully",
        "attempts": 1,
    }

    job = await store.create({"seconds": 0}, max_retries=3)
    final = await wait_for_job_status(store, job.id, JobStatus.COMPLETED)

    assert final.result == mock_process_job.return_value
    assert final.attempts == 1
    mock_process_job.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.worker.process_job", new_callable=AsyncMock)
async def test_worker_requeues_transient_error_until_success(mock_process_job, store, worker_pool):
    mock_process_job.side_effect = [
        TransientError("Simulated transient error on attempt 1"),
        TransientError("Simulated transient error on attempt 2"),
        {
            "slept_seconds": 0,
            "message": "Job completed successfully",
            "attempts": 3,
        },
    ]

    job = await store.create({"seconds": 0, "transient_failures": 2}, max_retries=3)
    final = await wait_for_job_status(store, job.id, JobStatus.COMPLETED)

    assert final.attempts == 3
    assert mock_process_job.await_count == 3


@pytest.mark.asyncio
@patch("app.worker.process_job", new_callable=AsyncMock)
async def test_worker_fails_permanent_error_without_retry(mock_process_job, store, worker_pool):
    mock_process_job.side_effect = ValueError("payload.seconds must be between 0 and 300")

    job = await store.create({"seconds": 0}, max_retries=3)
    final = await wait_for_job_status(store, job.id, JobStatus.FAILED)

    assert final.attempts == 1
    assert "payload.seconds" in final.error
    mock_process_job.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.worker.process_job", new_callable=AsyncMock)
async def test_worker_fails_when_transient_retries_are_exhausted(mock_process_job, store, worker_pool):
    mock_process_job.side_effect = TransientError("Simulated transient error on attempt 1")

    job = await store.create({"seconds": 0, "transient_failures": 5}, max_retries=0)
    final = await wait_for_job_status(store, job.id, JobStatus.FAILED)

    assert final.attempts == 1
    assert "Simulated transient error" in final.error
    mock_process_job.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.worker.process_job", new_callable=AsyncMock)
async def test_worker_fails_when_requeue_returns_false(mock_process_job, store, worker_pool):
    mock_process_job.side_effect = TransientError("Simulated transient error on attempt 1")

    with patch.object(store, "requeue", new_callable=AsyncMock) as mock_requeue:
        mock_requeue.return_value = False
        job = await store.create({"seconds": 0}, max_retries=3)
        final = await wait_for_job_status(store, job.id, JobStatus.FAILED)

    assert final.attempts == 1
    assert "Failed to requeue after transient error" in final.error
    mock_requeue.assert_awaited_once()
