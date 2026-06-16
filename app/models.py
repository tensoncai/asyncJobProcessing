from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobPayload(BaseModel):
    seconds: float = Field(default=1.0, ge=0, le=300)
    transient_failures: int = Field(default=0, ge=0, le=10)
    max_retries: int = Field(default=3, ge=0, le=10)

    @model_validator(mode="after")
    def transient_failures_must_be_retryable(self) -> JobPayload:
        if self.transient_failures > self.max_retries:
            raise ValueError(
                f"transient_failures ({self.transient_failures}) cannot exceed "
                f"max_retries ({self.max_retries})"
            )
        return self


class CreateJobRequest(BaseModel):
    payload: JobPayload = Field(default_factory=JobPayload)


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
