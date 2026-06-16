import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    from app.main import worker_pool
    from app.store import job_store

    job_store.reset_for_tests()
    await worker_pool.stop()
    await worker_pool.start()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await worker_pool.stop()


async def _wait_for_status(client, job_id: str, expected_status: str, *, attempts: int = 40):
    status_response = None
    for _ in range(attempts):
        status_response = await client.get(f"/jobs/{job_id}")
        if status_response.json()["status"] == expected_status:
            return status_response
        await asyncio.sleep(0.05)
    return status_response


@pytest.mark.asyncio
async def test_submit_and_poll_job(client):
    response = await client.post("/jobs", json={"payload": {"seconds": 0.1}})
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_response = await client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["id"] == job_id
    assert body["status"] in ("queued", "running", "completed")

    status_response = await _wait_for_status(client, job_id, "completed")
    final = status_response.json()
    assert final["status"] == "completed"
    assert final["result"]["slept_seconds"] == 0.1


@pytest.mark.asyncio
async def test_retries_transient_failures_until_success(client):
    response = await client.post(
        "/jobs",
        json={"payload": {"seconds": 0.05, "transient_failures": 2, "max_retries": 3}},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_response = await _wait_for_status(client, job_id, "completed")
    final = status_response.json()
    assert final["status"] == "completed"
    assert final["attempts"] == 3
    assert final["result"]["attempts"] == 3


@pytest.mark.asyncio
async def test_retries_exhausted_marks_job_failed(client):
    response = await client.post(
        "/jobs",
        json={"payload": {"seconds": 0.05, "transient_failures": 10, "max_retries": 2}},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_response = await _wait_for_status(client, job_id, "failed")
    final = status_response.json()
    assert final["status"] == "failed"
    assert final["attempts"] == 3
    assert "Simulated transient error" in final["error"]


@pytest.mark.asyncio
async def test_get_missing_job_returns_404(client):
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
