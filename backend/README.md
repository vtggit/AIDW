# AIDW Backend

This folder contains the backend API for AIDW, built with **FastAPI** on PostgreSQL
(psycopg2 raw-SQL repositories, Alembic migrations). The frontend in `app/` is a client that
talks to it exclusively through `/api`.

The same image also runs the **worker** process (`python -m app.worker`), which executes
ingestion runs, scheduled load sequences and deletion requests outside the API process.

## Capability areas

| Area | API prefixes | Supporting modules |
|------|--------------|--------------------|
| Sources and connections | `/api/sources`, `/api/source-connections`, `/api/source-credentials`, `/api/odata-service-configs`, `/api/connection-tests` | `app/egress/` |
| Schema discovery | `/api/sources/{id}/discover`, `/api/datasets`, `/api/discovered-fields`, `/api/discovery-runs` | `app/discovery/` |
| Ingestion and change data capture | `/api/pipelines`, `/api/runs`, `/api/delta-cursors`, `/api/ingested-records` | `app/ingest/`, `app/worker/` |
| Load sequences (ordered, schedulable pipeline runs) | `/api/load-sequences`, `/api/sequence-steps`, `/api/sequence-runs`, `/api/sequence-run-steps` | `app/scheduling/`, `app/worker/` |
| Profiling and PII detection | `/api/sources/{id}/profile`, `/api/field-profiles`, `/api/sources/{id}/pii-scan`, `/api/pii-flags` | `app/profiling/`, `app/pii/` |
| Retention | `/api/retention-policies`, `/api/retention-runs` | `app/retention/` |
| Right-to-be-forgotten erasure | `/api/deletion-requests`, `/api/suppression-entries`, `/api/workflows` | `app/governance/`, `app/workflows/` |
| Dashboards and suggestions | `/api/dashboards`, `/api/dashboard-items`, `/api/dashboard-item-fields`, `/api/dashboard-item-layouts`, `/api/suggestions`, `/api/suggestion-fields` | `app/dashboard/`, `app/suggestion/`, `app/series/` |
| Process definitions and BPMN generation | `/api/process-definitions`, `/api/process-steps`, `/api/sequence-flows` | `app/bpmn/` |
| Outbound OData v4 feed | `/api/feed/v4`, `/api/feed-credentials` | `app/feed/` |
| Audit | `/api/audit`, `/api/audit-logs` | `app/audit/` |
| Platform | `/api/health`, `/api/auth` | `app/auth/`, `app/observability/` |

OData is the only source connector kind implemented (`app/discovery/schema_reader.py`).

## Structure

```
backend/
├── Dockerfile            # python:3.11-slim, non-root user, entrypoint start.sh
├── start.sh              # waits for PostgreSQL, runs migrations, execs the command
├── run_tests.sh          # test runner against an ephemeral PostgreSQL container
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/         # 0001_baseline.py … one file per schema change
├── openapi.json          # committed API contract artifact
├── requirements.txt
├── app/
│   ├── main.py           # application factory, exception handlers, router mounts
│   ├── config.py         # application and database configuration (env-driven)
│   ├── api/              # one router module per resource
│   ├── services/         # business logic per resource
│   ├── repositories/     # PostgreSQL data access per resource
│   ├── models/           # Pydantic request/response models
│   ├── auth/             # authentication, role checks, public-route allowlist
│   ├── audit/            # audit recorder
│   ├── db/               # connection helper (schema.py is a deprecated reference)
│   ├── observability/    # structured logging, request-ID middleware
│   ├── egress/           # outbound HTTP, destination policy, secret references
│   ├── discovery/        # source schema readers
│   ├── ingest/           # run execution, cursor CDC, landing, field mapping
│   ├── worker/           # claim/execute/reap loop, sequence scheduling
│   ├── scheduling/       # cadence calculation for load sequences
│   ├── profiling/        # field profiling
│   ├── pii/              # PII detection engine
│   ├── retention/        # retention planner and reaper
│   ├── governance/       # deletion-request lifecycle, erasure executor, suppression hashing
│   ├── workflows/        # client for an optional Flowable sidecar
│   ├── dashboard/        # dashboard item data service
│   ├── series/           # dashboard item time series
│   ├── suggestion/       # dashboard-item suggestion engine
│   ├── bpmn/             # BPMN XML and SVG generation
│   └── feed/             # OData v4 feed: credential auth, $filter parsing, naming
└── tests/                # pytest suite (PostgreSQL-backed)
```

## Running the backend

### Full stack via Docker Compose (recommended)

From the repository root:

```bash
cp .env.example .env     # first time only; set DB_PASSWORD
docker compose up -d --build
```

The backend container:

1. Waits for PostgreSQL to accept connections (`start.sh`, 30 attempts, 2 s apart).
2. Runs `alembic upgrade head`. If a migration fails the container exits and the API does not start.
3. Starts uvicorn on port 9000.

Compose publishes the backend port on loopback only (`BACKEND_BIND_HOST`, default `127.0.0.1`);
browsers reach the API through the frontend's nginx at `/api/`, which enforces a 1 MB request-body
limit.

To run ingestion in the worker instead of the API process:

```bash
INGEST_EXECUTOR=worker docker compose --profile worker up -d --build
```

### Manual (no Docker)

Requires a running PostgreSQL and Python 3.11.

```bash
cd backend
pip install -r requirements.txt
export DB_HOST=localhost DB_NAME=aidw DB_USER=aidw DB_PASSWORD=change-me
export AUTH_MODE=development AUTH_DEV_TOKEN=dev-secret-token

alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000
```

## Authentication and authorization

Bearer-token authentication has two modes, selected by `AUTH_MODE`:

- `development`: accepts the shared bearer token `AUTH_DEV_TOKEN`. The token's roles come from
  `AUTH_DEV_ROLES` (default `user`; set `admin,user` to act as an admin).
- `production`: validates JWTs against the configured identity provider (JWKS signature
  verification, issuer, audience and expiry checks). Roles and groups are read from the claim
  paths in `AUTH_ROLE_CLAIMS` and `AUTH_GROUP_CLAIMS`.

Any other `AUTH_MODE` value fails closed: every token is rejected.

Only these routes are served without authentication (`app/auth/public_routes.py`):

| Method | Path |
|--------|------|
| GET | `/api/health` |
| GET | `/api/health/ready` |
| GET | `/api/health/version` |
| GET | `/api/auth/config` |

Every other `/api` route must reach an authentication dependency; a test walks the served
application and fails the build if one does not. Routes that need elevated access declare
`require_role("admin")`.

The OData feed under `/api/feed/v4` does not use bearer tokens. It authenticates machine clients
against feed credentials, presented as `Authorization: Basic base64(principal:key)` or
`X-Api-Key: <key>`. Feed credentials are managed at `/api/feed-credentials`.

## Configuration

All configuration comes from environment variables. `.env.example` at the repository root lists
the ones Docker Compose reads.

The code-level fallbacks for the database settings and `AUTH_CLIENT_ID` still carry the names of
the project this backend was bootstrapped from (`aicrm`, `aicrm-backend`). Docker Compose does not
rely on them: `DB_NAME`, `DB_USER` and `DB_PASSWORD` have no compose default and must be set in
`.env`.

### Database

| Variable | Code default | Description |
|----------|--------------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host (`db` under compose) |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `aicrm` | Database name (`.env.example`: `aidw`) |
| `DB_USER` | `aicrm` | Database user (`.env.example`: `aidw`) |
| `DB_PASSWORD` | `aicrm` | Database password |
| `DB_STATEMENT_TIMEOUT_MS` | empty | Per-statement timeout in milliseconds; empty means none |

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_VERSION` | unset | Overrides the reported version (see Health) |
| `GIT_SHA`, `BUILD_TIMESTAMP` | empty | Build metadata reported by the health endpoints |
| `ENVIRONMENT` | `development` | Environment label |
| `DEBUG` | `true` | Debug flag |
| `LOG_LEVEL` | `INFO` | Python log level |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080` | Comma-separated allowed origins |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | `true` | Enables the auth boundary |
| `AUTH_MODE` | `development` | `development` or `production`; anything else fails closed |
| `AUTH_DEV_TOKEN` | `dev-secret-token` | Shared bearer token for development mode |
| `AUTH_DEV_ROLES` | `user` | Comma-separated roles for the development token |
| `AUTH_ISSUER` | `https://dev.example.com/realms/aicrm` | Identity provider issuer URL (placeholder) |
| `AUTH_CLIENT_ID` | `aicrm-backend` | Client ID (compose default: `aidw-backend`) |
| `AUTH_AUDIENCE` | value of `AUTH_CLIENT_ID` | JWT audience to validate |
| `AUTH_JWKS_URL` | `{AUTH_ISSUER}/protocol/openid-connect/certs` | JWKS URL |
| `AUTH_ALGORITHMS` | `RS256` | Comma-separated allowed JWT algorithms |
| `AUTH_JWKS_CACHE_TTL` | `3600` | JWKS cache lifetime in seconds |
| `AUTH_ROLE_CLAIMS` | `roles,realm_access.roles,resource_access.{client_id}.roles` | Claim paths scanned for roles |
| `AUTH_GROUP_CLAIMS` | `groups` | Claim paths scanned for groups |

### Ingestion, egress and worker

| Variable | Default | Description |
|----------|---------|-------------|
| `INGEST_EXECUTOR` | `inline` | `inline` runs ingestion in the API process; `worker` only enqueues a pending run for the worker |
| `ENABLE_INAPI_EGRESS` | `false` | Allows the API process to call source systems: discovery, profiling, `inline` ingestion and live dashboard-item data |
| `EGRESS_POLICY` | unset | `strict` additionally denies loopback destinations |
| `EGRESS_ALLOWED_HOSTS` | unset | Comma-separated hostnames exempt from the egress denial rules |
| `WORKER_POLL_SECONDS` | `5` | Worker poll interval |
| `WORKER_STALE_RUNNING_SECONDS` | `1800` | Age after which a `running` run with no live executor is finalized `failed` |
| `WORKER_STRANDED_SCHEDULED_SECONDS` | `1800` | Equivalent cutoff for stranded scheduled sequence runs |

Link-local destinations, `0.0.0.0` and empty hosts are denied for egress in every mode
(`app/egress/policy.py`).

### OData feed

| Variable | Default | Description |
|----------|---------|-------------|
| `FEED_EXTERNAL_BASE_URL` | empty | External origin used in `@odata.context`, `@odata.nextLink` and service-document URLs |
| `FEED_TRUST_FORWARDED_HEADERS` | `false` | Derive the external origin from forwarded headers |
| `FEED_PAGE_SIZE` | `1000` | Server page size |
| `FEED_TOP_MAX` | `5000` | Maximum accepted `$top` |
| `FEED_METADATA_MAX_AGE` | `300` | Cache max-age for `$metadata`, in seconds |

### Governance and workflows

| Variable | Default | Description |
|----------|---------|-------------|
| `AIDW_SUPPRESSION_PEPPER` | unset | HMAC key for erased-subject hashes. Required to execute a deletion request; must be identical for the backend and the worker; rotating it orphans existing suppression entries. See `.env.example`. |
| `FLOWABLE_BASE_URL`, `FLOWABLE_REST_USER`, `FLOWABLE_REST_PASSWORD` | empty | Optional Flowable sidecar used by `/api/workflows`. The sidecar is not part of this repository's compose file. |

## API

`backend/openapi.json` is the authoritative list of routes and request/response shapes. Most
resources follow one pattern:

```
GET    /api/<resource>        list
POST   /api/<resource>        create
GET    /api/<resource>/{id}   read
PUT    /api/<resource>/{id}   update
DELETE /api/<resource>/{id}   delete
```

Routes beyond that pattern:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health`, `/api/health/ready`, `/api/health/version` | Liveness, readiness, version |
| GET | `/api/auth/config`, `/api/auth/me` | Public auth configuration; current user |
| GET | `/api/audit` | Audit events |
| POST | `/api/sources/{source_id}/discover` | Discover a source's schema |
| POST | `/api/sources/{source_id}/profile` | Profile a source's fields |
| POST | `/api/sources/{source_id}/pii-scan` | Scan a source for PII |
| POST | `/api/connection-tests/{entity_id}/run` | Run a connection test |
| POST | `/api/pipelines/{pipeline_id}/runs` | Trigger an ingestion run |
| GET | `/api/load-sequences/due` | Load sequences due to run |
| GET | `/api/load-sequences/{sequence_id}/bpmn` | BPMN rendering of a load sequence |
| POST | `/api/sequence-runs/{run_id}/execute` | Execute a sequence run |
| POST | `/api/pii-flags/{flag_id}/confirm`, `/dismiss` | Decide a PII flag |
| POST | `/api/retention-policies/{policy_id}/sweep` | Run a retention sweep |
| POST | `/api/deletion-requests/{entity_id}/verify`, `/reject` | Decide a deletion request |
| POST | `/api/workflows/rtbf/start` | Start an erasure workflow on the Flowable sidecar |
| GET | `/api/workflows/instances/{instance_id}` | Workflow instance status |
| POST | `/api/suggestions/{entity_id}/accept`, `/dismiss` | Decide a dashboard-item suggestion |
| GET | `/api/dashboard-items/{entity_id}/data`, `/series` | Data and time series for a dashboard item |
| POST | `/api/process-definitions/{definition_id}/generate`, `/validate` | Generate or validate BPMN for a process definition |
| POST | `/api/feed-credentials/{entity_id}/rotate` | Rotate a feed credential |
| GET | `/api/feed/v4`, `/api/feed/v4/$metadata`, `/api/feed/v4/{entity_set}` | OData v4 service document, metadata, entity sets |

### Error responses

| Status | When |
|--------|------|
| 409 | A write violates a unique constraint |
| 422 | Request validation fails, or a write violates a foreign-key or CHECK constraint |
| 503 | Any other database error |
| 500 | Unhandled exception |

Each of these bodies carries a `request_id`. Every response has an `X-Request-ID` header; an
incoming `X-Request-ID` is preserved, otherwise one is generated. The same ID appears in the
backend log lines for that request.

### Health

```bash
curl http://localhost:9000/api/health
# {"status": "ok", "app_version": "<version>", "service": "aidw-backend",
#  "git_sha": null, "build_timestamp": null}

curl http://localhost:9000/api/health/ready
# adds "dependencies": [{"name": "database", "status": "ok", "detail": null}]
```

`/api/health` does not call dependencies. `/api/health/ready` checks database connectivity and
reports `"status": "degraded"` when it fails. `git_sha` and `build_timestamp` are `null` unless
the `GIT_SHA` and `BUILD_TIMESTAMP` environment variables are set.

The reported version is `APP_VERSION` if set, otherwise the `VERSION` file at the repository
root, otherwise the fallback `0.1.0`. The Docker build context is `backend/`, which does not
contain `VERSION`, so a container reports `0.1.0` unless `APP_VERSION` is set.

## Database migrations

Schema changes go through Alembic migration files in `backend/migrations/versions/`, numbered
from `0001_baseline.py`. `start.sh` applies them on every container start; history is tracked in
the `alembic_version` table.

```bash
cd backend
alembic upgrade head     # apply pending migrations
alembic current          # show the applied revision
alembic history          # show the migration chain
```

`app/db/schema.py` is a deprecated reference and is not used for schema evolution.

## Worker

`python -m app.worker` (the compose `worker` service, profile `worker`) polls the database and:

- claims pending ingestion runs with `FOR UPDATE SKIP LOCKED` and executes them through the same
  code path as the in-API executor;
- fires load sequences that are due and executes scheduled sequence runs;
- executes deletion requests;
- finalizes as `failed` any `running` row whose executor died.

## Testing

The suite is PostgreSQL-backed. Tests run in development auth mode against a dedicated database
(`aicrm_test_db`, a name inherited from the bootstrap project) that the test session creates and
drops; your development database is not touched.

```bash
cd backend
./run_tests.sh              # starts the compose test-db service on port 5433, runs pytest, removes it
./run_tests.sh -k feed      # extra arguments are passed to pytest
```

With a local PostgreSQL whose user may create and drop databases, `pytest tests/ -v` works directly.

Frontend tests are Playwright specs under `app/tests/`.

## CI

`.github/workflows/backend-ci.yml` runs on pushes and pull requests to `main`. Changes that touch
only `docs/**` or Markdown files do not trigger it.

| Job | What it checks |
|-----|----------------|
| Release metadata | `VERSION` format and changelog consistency (`scripts/check_release_metadata.py`) |
| Quality gates | `black --check backend/`, `ruff check backend/`, shellcheck |
| Security hygiene | `pip-audit` on `requirements.txt`, gitleaks secret scan |
| API contract | `backend/openapi.json` matches the schema generated from the application |
| Backend tests | Migrations apply to a clean PostgreSQL 15, then the full pytest suite |

`.github/workflows/codeagent-merge-gate.yml` separately checks a pull request's acceptance-criteria
proof map; see [scripts/ca_gate/README.md](../scripts/ca_gate/README.md).

### API contract

When a route or model changes, regenerate and commit the contract artifact:

```bash
python3 scripts/export_openapi.py
```

### Code quality

Formatter and linter settings are in `pyproject.toml` at the repository root.

```bash
black --check backend/
ruff check backend/
shellcheck backend/run_tests.sh backend/start.sh
```
