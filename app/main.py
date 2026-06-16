import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes.jobs import router as jobs_router
from app.store import job_store
from app.worker import JobWorkerPool

logging.basicConfig(level=logging.INFO)

worker_pool = JobWorkerPool(job_store, worker_count=2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await worker_pool.start()
    yield
    await worker_pool.stop()


app = FastAPI(
    title="Async Job Processing API",
    description="Submit jobs for background processing and poll for status.",
    lifespan=lifespan,
)

app.include_router(jobs_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
