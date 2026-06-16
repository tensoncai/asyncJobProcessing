# Async Job Processing REST API

FastAPI service with a background worker pool for async job processing.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for interactive API docs.

## API

### Submit a job

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": {"seconds": 3, "transient_failures": 2, "max_retries": 3}}'
```

Returns `202 Accepted` with a job ID immediately. Processing happens in the background.

Payload fields:

- `seconds` — simulated work duration
- `transient_failures` — how many attempts should fail with a transient error before succeeding
- `max_retries` — max automated retries after the first attempt (default: 3)

### Check job status

```bash
curl http://127.0.0.1:8000/jobs/<job-id>
```

Response includes:

- `status`: `queued` | `running` | `completed` | `failed`
- `attempts` / `max_retries`: retry progress
- `result`: populated when completed
- `error`: populated when failed, or briefly after a transient failure before retry

## Architecture

```
POST /jobs  →  JobStore (queue + in-memory state)  →  Worker Pool
GET /jobs/{id}  →  JobStore
```

- **HTTP layer** returns immediately after enqueueing
- **Worker pool** (2 concurrent workers) pulls job IDs from an `asyncio.Queue`
- **Mock processor** sleeps for `payload.seconds` to simulate work
- **Retry logic** requeues jobs that fail with simulated transient errors until `max_retries` is exhausted

## Tests

```bash
source .venv/bin/activate
pytest -v
```

Test layout:

- `tests/test_handlers.py` — unit tests for job handler and payload validation
- `tests/test_worker.py` — unit tests for worker retry/requeue/failure behavior
- `tests/test_api.py` — integration tests for the HTTP API end-to-end

## CI/CD

GitHub Actions runs tests on every push and pull request to `main` (see `.github/workflows/ci.yml`).

## Deploy to DigitalOcean App Platform

DigitalOcean needs an explicit start command. This repo includes:

- **`Procfile`** — tells the platform how to start the server
- **`.do/app.yaml`** — optional App Platform spec

**Run command** (also set this in the DO dashboard if needed):

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

In the DigitalOcean UI:

1. Create App → connect your GitHub repo
2. **Resource type:** Web Service
3. **Build command:** `pip install -r requirements.txt`
4. **Run command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **HTTP port:** `8080`
6. **Instance count:** `1` (required — job store is in-memory)

Commit and push `Procfile`, then redeploy.

## Known limitations

This project is intentionally scoped for a single-process demo. Be aware of:

- **In-memory storage** — jobs are lost on server restart or redeploy
- **Single-process only** — the job store is not shared across multiple uvicorn workers or App Platform instances; running more than one process can cause intermittent `404 Job not found` on GET
- **API and workers are coupled** — workers run inside the API process, not as a separate deployable service
- **Bounded queue** — pending jobs are capped at 100; additional submissions receive `503 Service Unavailable`
- **Polling only** — clients must poll `GET /jobs/{id}`; there are no webhooks or push notifications
- **Mock processing** — jobs simulate work via `asyncio.sleep`; there is no real external task execution

For production, you would replace the in-memory dict with PostgreSQL or Redis, use a durable queue (SQS, RabbitMQ, Redis Streams), run workers as separate scaled services, and add webhooks for completion events.
