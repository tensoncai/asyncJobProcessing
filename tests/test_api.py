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


# --- Happy path ---


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
async def test_empty_payload_uses_defaults(client):
    response = await client.post("/jobs", json={"payload": {}})
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_response = await _wait_for_status(client, job_id, "completed")
    final = status_response.json()
    assert final["payload"]["seconds"] == 1.0
    assert final["max_retries"] == 3


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


# --- Submit-time validation (422) ---


@pytest.mark.asyncio
async def test_invalid_seconds_negative_returns_422(client):
    response = await client.post("/jobs", json={"payload": {"seconds": -1}})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_seconds_too_large_returns_422(client):
    response = await client.post("/jobs", json={"payload": {"seconds": 301}})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_seconds_type_returns_422(client):
    response = await client.post("/jobs", json={"payload": {"seconds": "fast"}})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_max_retries_returns_422(client):
    response = await client.post("/jobs", json={"payload": {"max_retries": 99}})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_transient_failures_exceeds_max_retries_returns_422(client):
    response = await client.post(
        "/jobs",
        json={"payload": {"transient_failures": 3, "max_retries": 2}},
    )
    assert response.status_code == 422
    assert "cannot exceed max_retries" in response.text


# --- GET edge cases ---


@pytest.mark.asyncio
async def test_get_missing_job_returns_404(client):
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_invalid_job_id_returns_422(client):
    response = await client.get("/jobs/not-a-uuid")
    assert response.status_code == 422


# --- Retry boundary ---


@pytest.mark.asyncio
async def test_transient_failures_at_max_retries_succeeds_on_last_allowed_attempt(client):
    """transient_failures=2, max_retries=2 → fails twice, succeeds on 3rd attempt."""
    response = await client.post(
        "/jobs",
        json={"payload": {"seconds": 0.05, "transient_failures": 2, "max_retries": 2}},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_response = await _wait_for_status(client, job_id, "completed")
    final = status_response.json()
    assert final["status"] == "completed"
    assert final["attempts"] == 3
