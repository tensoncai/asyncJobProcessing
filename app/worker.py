import asyncio
import logging

from app.jobs.errors import TransientError
from app.jobs.handlers import process_job
from app.store import JobStore

logger = logging.getLogger(__name__)


class JobWorkerPool:
    """Pulls jobs from the queue and processes them concurrently."""

    def __init__(self, store: JobStore, *, worker_count: int = 2) -> None:
        self._store = store
        self._worker_count = worker_count
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._worker_count):
            task = asyncio.create_task(self._run_worker(i), name=f"job-worker-{i}")
            self._tasks.append(task)
        logger.info("Started %d workers", self._worker_count)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Stopped workers")

    async def _run_worker(self, worker_id: int) -> None:
        while self._running:
            try:
                job_id = await self._store.dequeue()
            except asyncio.CancelledError:
                break

            job = None
            try:
                job = await self._store.mark_running(job_id)
                if job is None:
                    self._store.task_done()
                    continue

                logger.info(
                    "Worker %d running job %s (attempt %d/%d)",
                    worker_id,
                    job_id,
                    job.attempts,
                    job.max_retries + 1,
                )
                result = await process_job(job.payload, attempt=job.attempts)
                await self._store.mark_completed(job_id, result)
                logger.info("Worker %d finished job %s", worker_id, job_id)
            except TransientError as exc:
                if job is not None and job.attempts <= job.max_retries:
                    logger.warning(
                        "Worker %d retrying job %s after transient error: %s",
                        worker_id,
                        job_id,
                        exc,
                    )
                    await self._store.requeue(job_id, str(exc))
                else:
                    logger.error(
                        "Worker %d exhausted retries for job %s: %s",
                        worker_id,
                        job_id,
                        exc,
                    )
                    await self._store.mark_failed(job_id, str(exc))
            except Exception as exc:
                logger.exception("Worker %d failed job %s", worker_id, job_id)
                await self._store.mark_failed(job_id, str(exc))
            finally:
                self._store.task_done()
