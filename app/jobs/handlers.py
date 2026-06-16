import asyncio
from typing import Any

from app.jobs.errors import TransientError
from app.models import JobPayload


async def process_job(payload: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    """Mock job processor — sleeps to simulate work and can fail transiently."""
    job_input = JobPayload.model_validate(payload)
    seconds = job_input.seconds
    transient_failures = job_input.transient_failures

    if attempt <= transient_failures:
        raise TransientError(f"Simulated transient error on attempt {attempt}")

    await asyncio.sleep(seconds)
    return {
        "slept_seconds": seconds,
        "message": "Job completed successfully",
        "attempts": attempt,
    }
