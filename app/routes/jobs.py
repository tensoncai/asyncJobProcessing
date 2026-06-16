from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.jobs.errors import QueueFullError
from app.models import CreateJobRequest, CreateJobResponse, JobResponse
from app.store import Job, job_store

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        status=job.status,
        payload=job.payload,
        result=job.result,
        error=job.error,
        attempts=job.attempts,
        max_retries=job.max_retries,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(body: CreateJobRequest) -> CreateJobResponse:
    """Accept a job payload and return a job ID immediately."""
    payload = body.payload.model_dump()
    try:
        job = await job_store.create(payload, max_retries=body.payload.max_retries)
    except QueueFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return CreateJobResponse(id=job.id)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: UUID) -> JobResponse:
    """Return the current state and result for a job."""
    job = await job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _to_response(job)
