# AICRM Backend

This folder contains the backend API for AICRM, built with **FastAPI**.

## Architecture Overview

AICRM is a **backend-owned application**. All business data  —  Contacts, Leads, Activities, Templates, and Settings  —  is managed by the backend and persisted in PostgreSQL. The frontend is a client that communicates exclusively through this API.

### Domains

All major domains are PostgreSQL-backed:

| Domain      | Status    | CRUD Endpoints                          |
|-------------|-----------|------------------------------------------|
| Contacts    | Complete  | GET/POST/PUT/DELETE `/api/contacts`      |
| Leads       | Complete  | GET/POST/PUT/DELETE `/api/leads`         |
| Activities  | Complete  | GET/POST/PUT/DELETE `/api/activities`    |
| Templates   | Complete  | GET/POST/PUT/DELETE `/api/templates`     |
| Settings    | Complete  | GET/PUT `/api/settings`                  |

### Authentication

Two modes are supported:

- **Development mode** (`AUTH_MODE=development`): accepts a simple shared bearer token (`AUTH_DEV_TOKEN`).
- **Production mode** (`AUTH_MODE=production`): validates real JWTs against a configured identity provider using JWKS-based signature verification, issuer/audience validation, and token expiry checks.
- Roles and groups are normalized from IdP claims into a consistent application user context.
- Unknown `AUTH_MODE` values fail closed (no silent fallback to dev mode).

### Authorization

Role-based authorization is available via `require_role()` and `require_any_role()` dependencies.

### Audit Logging

Audit logging records mutations (create, update, delete) across all domains in a PostgreSQL `audit_log` table.

### Observability

Structured logging with per-request correlation IDs (`X-Request-ID`) is in place for operational observability.

### Versioning

The application version is defined in the **VERSION** file at the repository root.
The backend reads this file at startup and exposes the version via the health endpoint.

**Where version comes from:**

1. `APP_VERSION` environment variable (highest priority - useful for container deployments)
2. `VERSION` file at repo root (source of truth)
3. Hardcoded fallback `0.1.0` (safety net only)

**How version is exposed:**

```bash
curl http://localhost:9000/api/health
# Response: {"status": "ok", "app_version": "0.1.0", "service": "aicrm-backend"}
```

**Build / revision traceability:**

When `GIT_SHA` and/or `BUILD_TIMESTAMP` environment variables are set (e.g. by CI or
a Docker build step), the health endpoint includes additional traceability fields:

```bash
curl http://localhost:9000/api/health
# Response: {"status": "ok", "app_version": "0.1.0", "service": "aicrm-backend",
#            "git_sha": "abc1234", "build_timestamp": "2025-01-15T10:30:00Z"}
```

These values are never hardcoded in source. They are injected at build time via
environment variables so the running instance can be traced back to a specific
git commit and build time.

**CI validation of release metadata:**

CI runs `scripts/check_release_metadata.py` in a dedicated `release-metadata` job
that validates:

- `VERSION` file exists and is non-empty
- `VERSION` format is `MAJOR.MINOR.PATCH`
- `CHANGELOG.md` exists
- The current version appears in `CHANGELOG.md` (or an `[Unreleased]` section exists)
- If `VERSION` changes in a PR, `CHANGELOG.md` must also change

Run the check locally: `python3 scripts/check_release_metadata.py`

See [docs/operations/release-process.md](../docs/operations/release-process.md) for the full
versioning policy, release workflow, and which steps are automated vs manual.

## Structure

```
backend/
├── Dockerfile                # Container build definition
├── start.sh                  # Startup script (DB wait + migrations)
├── alembic.ini               # Alembic migration configuration
├── migrations/               # Versioned database migrations
│   ├── env.py                # Migration environment (reads env vars)
│   ├── script.py.mako        # Template for new migrations
│   └── versions/             # Individual migration files
│       └── 0001_baseline.py  # Baseline migration (current schema state)
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI application entry point
│   ├── config.py             # Application and database configuration
│   ├── auth/                 # Authentication and authorization layer
│   │   ├── __init__.py
│   │   ├── config.py         # Auth configuration (env-driven)
│   │   ├── models.py         # AuthUser model
│   │   ├── security.py       # Token validation helpers
│   │   ├── dependencies.py   # FastAPI route dependencies
│   │   └── authorization.py  # Role-based authorization helpers
│   ├── db/                   # Database connection and schema
│   │   ├── __init__.py
│   │   ├── connection.py     # PostgreSQL connection helper
│   │   └── schema.py         # DEPRECATED  —  kept as reference only
│   ├── api/                  # API route modules
│   │   ├── health.py         # Health check endpoint
│   │   ├── auth.py           # Auth endpoints (/me, /config)
│   │   ├── contacts.py       # Contacts CRUD endpoints
│   │   ├── leads.py          # Leads CRUD endpoints
│   │   ├── activities.py     # Activities CRUD endpoints
│   │   ├── templates.py      # Templates CRUD endpoints
│   │   ├── settings.py       # Settings endpoints
│   │   └── audit.py          # Audit log query endpoints
│   ├── services/             # Business logic layer
│   ├── repositories/         # Data access layer (all PostgreSQL-backed)
│   ├── models/               # Pydantic data models
│   └── observability/        # Operational observability
│       ├── __init__.py
│       ├── logging.py        # Structured logging configuration
│       └── middleware.py     # Request ID middleware
├── requirements.txt
├── openapi.json              # Committed API contract artifact
├── tests/                    # Automated test suite
│   ├── conftest.py           # Shared fixtures (DB, app, auth tokens)
│   ├── test_health_api.py    # Health endpoint tests
│   ├── test_auth_api.py      # Authentication tests
│   ├── test_authorization.py # Authorization tests
│   ├── test_contacts_api.py  # Contacts CRUD tests
│   ├── test_templates_api.py # Templates CRUD tests
│   ├── test_leads_api.py     # Leads CRUD tests
│   ├── test_activities_api.py # Activities CRUD tests
│   ├── test_settings_api.py  # Settings CRUD tests
│   ├── test_audit_api.py     # Audit logging tests
│   ├── test_migrations.py    # Migration tests
│   └── test_openapi_contract.py # API contract validation tests
└── README.md
```

## Running the Backend

### Option A: Full Stack via Docker Compose (Recommended)

From the repository root:

```bash
cp .env.example .env     # first time only
docker compose up --build
```

The backend container:
1. Waits for PostgreSQL to accept connections (`start.sh`)
2. Runs Alembic migrations (`alembic upgrade head`)
3. Starts uvicorn on port 9000

Migrations are applied automatically on every container start. The migration
history is tracked in the `alembic_version` table inside PostgreSQL.

### Option B: Manual (No Docker)

```bash
cd backend
pip install -r requirements.txt
export AUTH_MODE=development
export AUTH_DEV_TOKEN=dev-secret-token

# Run migrations first
alembic upgrade head

# Then start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000
```

The server starts at `http://localhost:9000`.

## Database

### Dependency

The backend requires PostgreSQL 12+. In docker-compose mode, the `db` service is started first and the backend waits for it via `start.sh`. In manual mode, start PostgreSQL yourself before running the backend.

### Schema Versioning with Alembic

Schema changes are managed through **Alembic**, a versioned migration tool.
All schema evolution happens through migration files in `backend/migrations/versions/`.

**Key principles:**

- Schema changes are **versioned, ordered, reviewable, and repeatable**.
- The baseline migration (`0001_baseline.py`) represents the current schema state at the time this system was introduced.
- New schema changes are introduced by creating a new migration file  —  not by editing `schema.py`.
- Migrations are applied automatically on container startup via `start.sh`.
- Migration history is tracked in the `alembic_version` table inside PostgreSQL.

### Migration Workflow

**Create a new migration:**

```bash
cd backend
alembic revision --autogenerate -m "add_new_column_to_contacts"
```

This creates a new file in `migrations/versions/` with the detected schema diff.
Always review the generated migration before applying it.

**Apply pending migrations:**

```bash
cd backend
alembic upgrade head
```

**Check current migration status:**

```bash
cd backend
alembic current     # shows the currently applied revision
alembic history     # shows the full migration chain
```

**Downgrade one step (use with caution):**

```bash
cd backend
alembic downgrade -1
```

### Startup Order (Containerized)

```
db (PostgreSQL)
  → healthcheck passes (pg_isready)
    → backend (start.sh waits for DB connectivity)
      → alembic upgrade head (applies pending migrations)
        → uvicorn starts
          → API is ready
```

### Legacy Schema Helper

The file `backend/app/db/schema.py` is retained temporarily as a reference
for the current schema structure. It is **no longer** the primary mechanism
for schema evolution. New schema changes should always go through Alembic
migrations.

## Configuration

All configuration is driven by environment variables with explicit, safe defaults. There are no hidden fallback paths. See `.env.example` at the repository root for the complete list.

### Database

| Variable       | Default     | Description          |
|----------------|-------------|----------------------|
| `DB_HOST`      | `localhost` | PostgreSQL host      |
| `DB_PORT`      | `5432`      | PostgreSQL port      |
| `DB_NAME`      | `aicrm`     | Database name        |
| `DB_USER`      | `aicrm`     | Database username    |
| `DB_PASSWORD`  | `aicrm`     | Database password    |

### Application

| Variable      | Default       | Description                          |
|---------------|---------------|--------------------------------------|
| `ENVIRONMENT` | `development` | Environment label                    |
| `DEBUG`       | `true`        | Enable FastAPI debug mode            |
| `CORS_ORIGINS`| (see below)   | Comma-separated allowed origins      |

Default CORS origins: `http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080`

### Authentication

| Variable             | Default                                              | Description                                      |
|----------------------|------------------------------------------------------|--------------------------------------------------|
| `AUTH_ENABLED`       | `true`                                               | Enable/disable auth boundary                     |
| `AUTH_MODE`          | `development`                                        | `development` or `production` (fail closed for unknown values) |
| `AUTH_DEV_TOKEN`     | `dev-secret-token`                                   | Shared bearer token for dev mode                 |
| `AUTH_DEV_ROLES`     | `user`                                               | Comma-separated roles for dev token              |
| `AUTH_ISSUER`        | `https://dev.example.com/realms/aicrm`               | IdP issuer URL (production mode)                 |
| `AUTH_CLIENT_ID`     | `aicrm-backend`                                      | Client ID / audience                             |
| `AUTH_AUDIENCE`      | (same as `AUTH_CLIENT_ID`)                           | JWT audience claim to validate                   |
| `AUTH_JWKS_URL`      | (derived from `AUTH_ISSUER`)                         | JWKS discovery URL                               |
| `AUTH_ALGORITHMS`    | `RS256`                                              | Comma-separated list of allowed JWT algorithms   |
| `AUTH_JWKS_CACHE_TTL`| `3600`                                               | JWKS cache TTL in seconds                        |
| `AUTH_ROLE_CLAIMS`   | `roles,realm_access.roles,resource_access.{client_id}.roles` | Dot-notation claim paths to scan for roles |
| `AUTH_GROUP_CLAIMS`  | `groups`                                             | Dot-notation claim paths to scan for groups      |

**Development mode example:**

```bash
export AUTH_MODE=development
export AUTH_DEV_TOKEN=my-dev-token
```

**Production mode example:**

```bash
export AUTH_MODE=production
export AUTH_ISSUER=https://your-idp.example.com/realms/aicrm
export AUTH_CLIENT_ID=aicrm-backend
export AUTH_JWKS_URL=https://your-idp.example.com/realms/aicrm/protocol/openid-connect/certs
```

### Logging

| Variable    | Default | Description                              |
|-------------|---------|------------------------------------------|
| `LOG_LEVEL` | `INFO`  | Python log level (DEBUG, INFO, WARNING, ERROR) |

Logs are written to stdout in a structured format that includes timestamp, level, request ID, logger name, and message. Example:

```
2024-01-15T10:30:00+0000 INFO   [a1b2c3d4-...] app.auth.security: JWT validation failed  —  token expired request_id=a1b2c3d4-...
```

## Available Endpoints

| Method | Path                        | Auth     | Description                |
|--------|-----------------------------|----------|----------------------------|
| GET    | `/`                         | No       | Root endpoint              |
| GET    | `/api/health`               | No       | Health check               |
| GET    | `/api/auth/config`          | No       | Public auth config         |
| GET    | `/api/auth/me`              | Yes      | Current user context       |
| GET    | `/api/contacts`             | Yes      | List all contacts          |
| POST   | `/api/contacts`             | Yes      | Create a contact           |
| PUT    | `/api/contacts/{id}`        | Yes      | Update a contact           |
| DELETE | `/api/contacts/{id}`        | Yes      | Delete a contact           |
| GET    | `/api/leads`                | Yes      | List all leads             |
| POST   | `/api/leads`                | Yes      | Create a lead              |
| GET    | `/api/leads/{id}`           | Yes      | Get a lead by ID           |
| PUT    | `/api/leads/{id}`           | Yes      | Update a lead              |
| DELETE | `/api/leads/{id}`           | Yes      | Delete a lead              |
| GET    | `/api/activities`           | Yes      | List all activities        |
| POST   | `/api/activities`           | Yes      | Create an activity         |
| PUT    | `/api/activities/{id}`      | Yes      | Update an activity         |
| DELETE | `/api/activities/{id}`      | Yes      | Delete an activity         |
| GET    | `/api/templates`            | Yes      | List all templates         |
| POST   | `/api/templates`            | Yes      | Create a template          |
| PUT    | `/api/templates/{id}`       | Yes      | Update a template          |
| DELETE | `/api/templates/{id}`       | Yes      | Delete a template          |
| GET    | `/api/settings`             | Yes      | Get application settings   |
| PUT    | `/api/settings`             | Yes      | Update application settings |
| GET    | `/api/audit`                | Yes      | List audit events          |

Routes marked **Yes** require a valid Bearer token. In development mode, use the value of `AUTH_DEV_TOKEN` (default: `dev-secret-token`).

## Request Correlation

Every request is assigned a unique correlation ID, exposed in the `X-Request-ID` response header. If the incoming request already carries an `X-Request-ID` header, it is preserved; otherwise a new UUID is generated. This ID is included in all backend log lines, making it easy to trace a single request through the full stack:

```bash
curl -v http://localhost:9000/api/contacts \
  -H "Authorization: Bearer dev-secret-token"
# Response header: X-Request-ID: <uuid>
```

## Troubleshooting

### Health Endpoints

The backend provides two health endpoints for operational diagnostics:

```bash
# Basic liveness check (returns 200 if the process is running)
curl http://localhost:9000/api/health

# Readiness check (includes database connectivity status)
curl http://localhost:9000/api/health/ready
```

The readiness endpoint returns `"status": "degraded"` if the database is unreachable, even though the process itself is running. Use this to distinguish between "backend down" and "backend running but database unavailable."

Response fields:
- `status`: `"ok"` or `"degraded"`
- `app_version`: Application version from `VERSION` file or `APP_VERSION` env var
- `service`: Always `"aicrm-backend"`
- `git_sha`: Git commit SHA (if `GIT_SHA` env var is set)
- `build_timestamp`: Build timestamp (if `BUILD_TIMESTAMP` env var is set)
- `dependencies`: Object with dependency status (e.g., `{"database": {"status": "ok"|"error", "error": "..."}}`)

### Backend Not Starting

**Symptoms:** Backend container exits, process crashes, or port 9000 is not listening.

**Diagnostics:**
```bash
# Check if the process is running
docker ps -a | grep aicrm-backend

# View startup logs (look for [startup] prefixed lines)
docker logs aicrm-backend --tail 50

# Check for port conflicts
lsof -i :9000
```

**Startup log prefixes and their meaning:**
- `[startup] INFO: Waiting for PostgreSQL...`  —  Normal: backend is waiting for DB
- `[startup] INFO: PostgreSQL is ready`  —  Normal: DB connection established
- `[startup] INFO: Running database migrations...`  —  Normal: applying schema migrations
- `[startup] INFO: Migrations completed`  —  Normal: schema is up to date
- `[startup] ERROR: PostgreSQL ... did not become ready`  —  DB is down or unreachable after 60s
- `[startup] ERROR: Database migrations failed`  —  Migration error (see below)

**Common causes:**
- **Database not ready:** Backend waits 60 seconds. If DB doesn't start, the backend exits with a clear error. Start the database first.
- **Port conflict:** Another process is using port 9000. Kill it or change `BACKEND_PORT`.
- **Missing Python dependencies:** Rebuild the container image.

### Database Connection Failure

**Symptoms:**
- Frontend shows "The service is temporarily unavailable" on API requests
- `/api/health/ready` returns `"status": "degraded"` with database error
- Backend logs show `psycopg2.OperationalError` or connection refused errors

**Diagnostics:**
```bash
# Check if PostgreSQL is running
docker ps | grep aicrm-db

# Test database connectivity
docker exec -it aicrm-db psql -U aicrm -d aicrm -c "SELECT 1"

# Check backend logs for connection errors
docker logs aicrm-backend --tail 50 | grep -i "database\|postgres\|psycopg"

# Check readiness endpoint
curl http://localhost:9000/api/health/ready
```

**Common causes:**
- **Database container not started:** `docker start aicrm-db`
- **Database still initializing:** PostgreSQL can take 10-30 seconds to start. Wait or restart backend.
- **Wrong credentials:** Verify DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD environment variables.
- **Network issue:** Containers must be on the same Docker network.

### Migration Failure

**Symptoms:**
- Backend logs show `[startup] ERROR: Database migrations failed`
- Backend process exits with non-zero code
- Error references a specific migration file or SQL error

**Diagnostics:**
```bash
# View migration error details
docker logs aicrm-backend --tail 100 | grep -A 20 "migration"

# Check current migration version
docker exec -it aicrm-db psql -U aicrm -d aicrm -c "SELECT version_num FROM alembic_version"

# Check migration history
docker exec aicrm-backend alembic history
docker exec aicrm-backend alembic current
```

**Common causes:**
- **Stale schema:** Database was modified outside of migrations. Inspect with `alembic current` and `alembic heads`.
- **Conflicting migrations:** Two HEAD revisions exist. Resolve with `alembic merge head`.
- **Missing migration:** New code references tables not yet created. Create the migration with `alembic revision --autogenerate -m "description"`.
- **Permission issue:** PostgreSQL user lacks CREATE/ALTER privileges.

**Recovery:**
```bash
# If safe to stamp (schema manually matches a known revision)
docker exec aicrm-backend alembic stamp <revision>

# Re-run migrations
docker exec aicrm-backend alembic upgrade head
```

### Authentication Failures

**Symptoms:** Frontend shows "You must sign in to perform this action" or API returns 401.

**Diagnostics:**
```bash
# Check auth-related log lines
docker logs aicrm-backend --tail 50 | grep -i "auth\|token\|401"
```

**Auth failure types (check backend logs):**

| Log message | Meaning | Resolution |
|---|---|---|
| `auth: unauthenticated access attempt` | No token provided | User needs to log in |
| `auth: token validation failed  —  ExpiredSignatureError` | Token expired | Log in again |
| `auth: token validation failed  —  InvalidSignatureError` | Token is invalid | Clear localStorage, log in again |
| `auth: token validation failed  —  InvalidIssuerError` | Issuer mismatch | Check AUTH_ISSUER config |
| `auth: token validation failed  —  InvalidAudienceError` | Audience mismatch | Check AUTH_AUDIENCE config |
| `auth: JWKS fetch failed` | Can't reach auth provider | Check network and AUTH_JWKS_URI |
| `auth: development mode  —  accepting any token` | Dev mode active | Expected in development |

**Auth configuration:**
- `AUTH_MODE=development`: Accepts any non-empty bearer token matching `AUTH_DEV_TOKEN`
- `AUTH_MODE=production`: Validates real JWTs against JWKS endpoint
- Unknown AUTH_MODE values cause startup failure (fail closed, no silent fallback)

**Common causes:**
- **Expired token:** Normal. User logs in again.
- **Stale token in browser:** Clear browser localStorage and log in again.
- **Auth mode misconfiguration:** Verify AUTH_MODE is "development" or "production".
- **JWKS unreachable:** Production mode requires network access to AUTH_JWKS_URI.

### Forbidden Action (403)

**Symptoms:** Frontend shows "You do not have permission to perform this action" or API returns 403.

**Diagnostics:**
```bash
# Check authorization log lines
docker logs aicrm-backend --tail 50 | grep -i "forbidden\|403\|admin"
```

The log line prefixed with `authz: forbidden` includes the user's subject, required role, and actual roles.

**Common causes:**
- **Non-admin user accessing admin features:** Expected. Only admin users can access settings and audit logs.
- **Token missing is_admin claim:** If the user should be admin, re-authenticate with correct claims.
- **Frontend showing admin UI to non-admin users:** Admin-only elements should be hidden. If visible, it's a frontend bug.

### Audit Write Failure

**Symptoms:**
- API mutations fail with 500 errors
- Backend logs show `audit: failed to write event`

**Current behavior (Option B):**
When an audit write fails, the entire business mutation fails. This ensures every persisted mutation has a corresponding audit record. See `backend/app/services/audit_service.py` for the policy rationale.

**Diagnostics:**
```bash
# Check audit-related log lines
docker logs aicrm-backend --tail 50 | grep -i "audit"

# Verify audit_log table is accessible
docker exec -it aicrm-db psql -U aicrm -d aicrm -c "SELECT count(*) FROM audit_log"
```

**Common causes:**
- **Audit table missing:** Run migrations (`alembic upgrade head`).
- **Database permissions:** Grant INSERT on audit_log to the application user.
- **Database disk full:** Free disk space or expand volume.

### Request ID Tracing

Every request carries a unique `X-Request-ID` (UUID), included in response headers and all backend log lines. Use this to trace a specific request:

1. Note the `X-Request-ID` from the response header or error message
2. Search logs: `docker logs aicrm-backend | grep "<request_id>"`
3. This shows the complete log trail for that request

```bash
# Example: trace a request
curl -v http://localhost:9000/api/contacts \
  -H "Authorization: Bearer dev-secret-token"
# Note the X-Request-ID from response headers
# Then: docker logs aicrm-backend | grep "a1b2c3d4-..."
```

### Backend Port / Config Mismatch

**Symptoms:** Frontend can't reach backend, but backend health check works on a different port.

**Diagnostics:**
```bash
# Check what port the backend is actually listening on
docker logs aicrm-backend --tail 20 | grep "Uvicorn"

# Check frontend configuration
grep "API_BASE_URL" app/js/api.js
```

The frontend connects to the backend via the `API_BASE_URL` constant in `app/js/api.js`. In docker-compose mode, this defaults to the backend service URL. If you've changed the backend port, update this accordingly.

## Testing

### Running the Test Suite

The backend has an automated test suite covering API behavior, authentication,
authorization, audit logging, and database migrations. There are two ways to
run the tests.

#### Option 1: Containerized PostgreSQL (Recommended)

The simplest approach uses a containerized PostgreSQL test database. This
requires only Docker  —  no host PostgreSQL installation needed.

```bash
cd backend
./run_tests.sh              # run all tests
./run_tests.sh -k test_auth # pass extra pytest args
```

The script starts an ephemeral PostgreSQL container on port 5433, runs the
test suite, and tears down the container automatically. It never touches your
normal development database.

#### Option 2: Local PostgreSQL

If you have PostgreSQL running locally, you can run pytest directly:

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

The test suite uses a dedicated test database (`aicrm_test_db`) that is
created and destroyed automatically per test session. It will **never**
touch your normal development database.

### Prerequisites

**Option 1 (containerized):** Docker must be installed and accessible.

**Option 2 (local PostgreSQL):**
- PostgreSQL 12+ running and accessible at the configured `DB_HOST`/`DB_PORT`
- The configured database user must have permission to create/drop databases

### Test Categories

| Test File | Category | What It Covers |
|-----------|----------|----------------|
| `test_health_api.py` | Health | `/api/health` returns success |
| `test_auth_api.py` | Authentication | Token validation, role normalization, 401 for missing/invalid tokens |
| `test_authorization.py` | Authorization | 401 for unauthenticated, 403 for non-admin mutations, admin access succeeds |
| `test_contacts_api.py` | Domain CRUD | Full CRUD on contacts with auth/authz guards |
| `test_templates_api.py` | Domain CRUD | Full CRUD on templates with auth/authz guards |
| `test_leads_api.py` | Domain CRUD | Full CRUD on leads with auth/authz guards |
| `test_activities_api.py` | Domain CRUD | Full CRUD on activities with auth/authz guards |
| `test_settings_api.py` | Domain CRUD | Read/update settings with auth/authz guards |
| `test_audit_api.py` | Audit | Audit records written for mutations, actor identity captured, admin-only access |
| `test_migrations.py` | Migrations | Clean migration apply, core tables exist, schema correctness, downgrade/re-upgrade |

### Test Configuration Assumptions

- Tests run in **development auth mode** (`AUTH_MODE=dev`) for fast, deterministic results.
- Admin and non-admin users are simulated via development tokens with different roles.
- Each test starts with a clean database (all application tables are truncated).
- The test database is isolated from the production database by name.

### CI Integration

Backend CI is automated via GitHub Actions (`.github/workflows/backend-ci.yml`).
The workflow runs on every push and pull request to `main`/`master`.

**CI jobs (in order of execution):**

1. **Release metadata**  —  validates `VERSION` format, changelog consistency, and drift detection (no database required)
2. **Quality gates**  —  Python formatting (black), linting (ruff), and shell checks (shellcheck) (no database required)
3. **Security hygiene**  —  dependency vulnerability scanning (pip-audit) and secret detection (gitleaks) (no database required)
4. **API contract**  —  validates `backend/openapi.json` stays in sync with the live FastAPI schema (requires backend dependencies)
5. **Backend tests**  —  full DB-backed test suite

**CI test path (backend-tests job):**

1. A PostgreSQL 15 service container is started by GitHub Actions
2. Alembic migrations are applied to verify they work on a clean database
3. The full pytest suite runs against the PostgreSQL-backed test database

The CI environment uses the same test database name and credentials as the
local containerized runner, just with a native service container instead of
Docker Compose:

| Variable | CI Value |
|----------|---------|
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `aicrm` |
| `DB_USER` | `aicrm` |
| `DB_PASSWORD` | `change-me-in-production` |
| `AUTH_MODE` | `development` |
| `AUTH_DEV_TOKEN` | `dev-secret-token` |

**Local vs CI comparison:**

| Aspect | Local (`./run_tests.sh`) | CI (GitHub Actions) |
|--------|--------------------------|---------------------|
| PostgreSQL | Docker Compose ephemeral container | GitHub Actions service container |
| Port | 5433 | 5432 |
| Test DB | `aicrm_test_db` (created by conftest) | `aicrm_test_db` (created by conftest) |
| Migrations | Applied by conftest + explicit step in CI | Applied explicitly + by conftest |
| Test command | `pytest tests/ -v --tb=short` | `pytest tests/ -v --tb=short` |
| Result | Local output | PR check status |

Both paths run the same real DB-backed test suite  —  CI does not substitute a
watered-down version. Migration failures and test failures appear as distinct
CI steps for clear visibility.

## Code Quality

The backend enforces automated quality gates for Python code and shell scripts.
These run in CI before the test suite and can be executed locally.

### Tools

| Tool | Purpose | Config |
|------|---------|--------|
| [black](https://black.readthedocs.io/) | Deterministic Python formatting | `pyproject.toml` |
| [ruff](https://docs.astral.sh/ruff/) | Fast Python linting (practical rules) | `pyproject.toml` |
| [shellcheck](https://www.shellcheck.net/) | Shell script static analysis |  —  |

### Local Commands

Run from the repository root:

```bash
# Check formatting (fails if any file needs formatting)
black --check backend/

# Auto-format all backend Python files
black backend/

# Check linting
ruff check backend/

# Auto-fix safe lint issues
ruff check backend/ --fix

# Check shell scripts
shellcheck backend/run_tests.sh backend/start.sh
```

### What the Rules Enforce

**black** enforces consistent, deterministic formatting. There are no style
arguments  —  if black says the file is wrong, run `black backend/` to fix it.

**ruff** catches practical problems including:
- Unused imports
- Undefined names
- Duplicate imports
- Obvious code simplifications
- Common bug patterns

The ruleset is intentionally modest. It focuses on catching real problems
without generating style noise. See `pyproject.toml` for the active rules.

### CI Integration

The "Quality gates" CI job runs black, ruff, and shellcheck before the
backend test job. It does not require a database, so it completes quickly
and fails fast. If a PR introduces a formatting or linting problem, CI will
reject it before the test suite even starts.

## Known Gaps and Future Work

1. End-to-end SSO login UX (redirect flow, logout, token refresh).
2. Expand role-based access control to cover all domains uniformly.
3. Metrics collection and alerting (Prometheus/Grafana).
4. Automated backup and restore tooling for PostgreSQL.
5. Frontend UI automation (backend coverage is now the priority).

## API Contract Discipline

AICRM treats the backend API as an explicit contract, not just a set of working routes. This section describes the contract discipline introduced in Step 27.

### Why

Backend route changes should be treated as **contract changes**, not casual implementation edits. This does not mean freezing everything forever  —  it means making changes explicit, reviewable, and less surprising.

### Request/Response Models

All migrated domain endpoints use explicit Pydantic request/response models consistently:

- **Contacts**: `ContactCreate`, `ContactUpdate`, `ContactResponse`
- **Templates**: `TemplateCreate`, `TemplateUpdate`, `TemplateResponse`
- **Leads**: `LeadCreate`, `LeadUpdate`, `LeadResponse`
- **Activities**: `ActivityCreate`, `ActivityUpdate`, `ActivityResponse`
- **Settings**: `SettingsUpdate`, `SettingsResponse`
- **Audit**: `AuditEventResponse`
- **Auth**: `AuthUser`, `MeResponse`, `AuthConfigResponse`
- **Health**: `HealthResponse`

No ad hoc dict shapes. No inconsistent field presence across similar routes.

### Response Shape Conventions

- **List endpoints** return raw arrays consistently (e.g., `GET /api/contacts` → `[{...}, ...]`).
- **Detail/mutation endpoints** return the authoritative record object.
- **Error responses** use FastAPI defaults unless a standard error model is introduced later.

### OpenAPI Schema as Contract Artifact

The OpenAPI schema generated by FastAPI is treated as a meaningful contract artifact:

- **Artifact location**: `backend/openapi.json`
- **Export script**: `scripts/export_openapi.py`
- **Regenerate**: `python3 scripts/export_openapi.py`

When you change an endpoint schema, you must regenerate and commit the contract artifact. CI will fail if the committed artifact diverges from the live schema.

### CI Enforcement

The `contract-check` CI job validates that `backend/openapi.json` stays in sync with the live FastAPI application. If a PR changes an endpoint model or route without updating the contract artifact, CI fails with a diff showing the drift.

### Developer Guidance

When making API changes:

1. Update the Pydantic models in `backend/app/models/`
2. Update route `response_model` declarations in `backend/app/api/`
3. Regenerate the contract artifact: `python3 scripts/export_openapi.py`
4. Commit both the code changes and the updated `backend/openapi.json`
5. Review the diff in `backend/openapi.json` to confirm the API surface change is intentional

### Frontend Alignment

Frontend data-source modules and the API client (`app/js/api.js`) are expected to match the now-explicit API contract. When reviewing backend changes, the committed OpenAPI schema serves as the reference for expected request/response shapes.

## Operational Ownership

The backend is the operational core of AICRM. The following expectations apply to anyone maintaining it.

### Maintenance Tasks for Backend Maintainers

| Task | Frequency | What to Do |
|------|-----------|-----------|
| Review failed CI runs | As they occur | Investigate and resolve quality gate, security hygiene, contract, or test failures |
| Review dependency hygiene | Monthly | Run `pip-audit -r backend/requirements.txt`; patch critical vulnerabilities |
| Review migration changes | Every schema change | Verify correctness, rollback safety, and data impact before merging |
| Verify environment configuration | Monthly | Confirm environment variables and auth settings have not drifted |
| Keep runbooks current | When behavior changes | Update `docs/operations/runbook.md` when new failure modes are discovered |

### Where to Find Operational Documentation

- **Runbook:** [docs/operations/runbook.md](../docs/operations/runbook.md)  —  first-response guidance for incidents
- **Support and Maintenance Model:** [docs/operations/support-maintenance-model.md](../docs/operations/support-maintenance-model.md)  —  ownership, recurring tasks, incident expectations
- **Release Process:** [docs/operations/release-process.md](../docs/operations/release-process.md)  —  version management and release workflow
- **Known Issues:** [docs/operations/known-issues.md](../docs/operations/known-issues.md)  —  track of known operational issues
