import pytest

from app.jobs.errors import TransientError
from app.jobs.handlers import process_job
from app.models import JobPayload


@pytest.mark.asyncio
async def test_process_job_completes_immediately_when_no_transient_failures():
    result = await process_job({"seconds": 0}, attempt=1)

    assert result["slept_seconds"] == 0
    assert result["attempts"] == 1
    assert result["message"] == "Job completed successfully"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt, transient_failures",
    [
        (1, 1),
        (1, 2),
        (2, 2),
    ],
)
async def test_process_job_raises_transient_error_on_configured_attempts(
    attempt, transient_failures
):
    with pytest.raises(TransientError, match=f"attempt {attempt}"):
        await process_job(
            {"seconds": 0, "transient_failures": transient_failures},
            attempt=attempt,
        )


@pytest.mark.asyncio
async def test_process_job_runs_after_transient_failure_window():
    result = await process_job({"seconds": 0, "transient_failures": 2}, attempt=3)

    assert result["attempts"] == 3
    assert result["slept_seconds"] == 0


def test_job_payload_rejects_impossible_retry_configuration():
    with pytest.raises(ValueError, match="cannot exceed max_retries"):
        JobPayload(seconds=1, transient_failures=3, max_retries=2)


def test_job_payload_defaults():
    payload = JobPayload()

    assert payload.seconds == 1.0
    assert payload.transient_failures == 0
    assert payload.max_retries == 3
