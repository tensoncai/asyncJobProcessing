import asyncio
from typing import Any

from app.jobs.errors import TransientError

DEFAULT_MAX_RETRIES = 3


def max_retries_from_payload(payload: dict[str, Any]) -> int:
    max_retries = int(payload.get("max_retries", DEFAULT_MAX_RETRIES))
    if max_retries < 0 or max_retries > 10:
        raise ValueError("payload.max_retries must be between 0 and 10")
    return max_retries


async def process_job(payload: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    """Mock job processor — sleeps to simulate work and can fail transiently."""
    seconds = float(payload.get("seconds", 1))
    if seconds < 0 or seconds > 300:
        raise ValueError("payload.seconds must be between 0 and 300")

    transient_failures = int(payload.get("transient_failures", 0))
    if transient_failures < 0 or transient_failures > 10:
        raise ValueError("payload.transient_failures must be between 0 and 10")

    if attempt <= transient_failures:
        raise TransientError(f"Simulated transient error on attempt {attempt}")

    await asyncio.sleep(seconds)
    return {
        "slept_seconds": seconds,
        "message": "Job completed successfully",
        "attempts": attempt,
    }
