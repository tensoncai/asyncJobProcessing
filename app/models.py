from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateJobRequest(BaseModel):
    payload: dict[str, Any] = Field(
        default_factory=dict,
        examples=[{"seconds": 2, "transient_failures": 1, "max_retries": 3}],
        description=(
            "Job input. Use seconds to simulate work duration, transient_failures "
            "to simulate flaky failures, and max_retries to cap automated retries."
        ),
    )


class CreateJobResponse(BaseModel):
    id: UUID


class JobResponse(BaseModel):
    id: UUID
    status: JobStatus
    payload: dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    attempts: int = 0
    max_retries: int = 3
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
