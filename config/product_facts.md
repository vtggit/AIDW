# AIDW Deployment Facts — authoritative answers for factual panel questions

Ground truth for the panel/auto-operator. `[OPERATOR: fill in]` marks unknowns; none are open
today. Last checked against the code and the persistent stack on 2026-11-02.

## What AIDW is

- An ERP-agnostic, self-hosted data warehouse AND data-governance platform: connect sources
  (OData-first), discover schema, ingest with CDC, profile data and flag PII, enforce retention
  and right-to-be-forgotten erasure, author/generate BPMN processes, dynamically suggest
  dashboard items, and publish ingested datasets as an OData v4 feed. An AI assistant panel can
  be attached; it is a separate service, not part of this repository. See product_vision.md.
- **Development and demonstration software, not for production use.** Its databases hold
  disposable test data and it never holds live production data.

## Hosting & infrastructure

- **Self-hosted, on-premises** — co-located with sibling products (AICRM among them) on a
  private-network host, but a **separate workspace and separate repo** (`vtggit/AIDW`). Do NOT
  assume OS-level isolation between the co-located products when reasoning about secret custody
  or blast radius — the deployment does not provide it.
- **This repository is PUBLIC.** Never write host addresses, credentials, customer names or
  internal strategy into tracked files; internal working docs are gitignored at the repo root.
- Orchestration: **docker-compose**. No Kubernetes/ECS.
- PostgreSQL: a **Docker container (postgres:15-alpine)** on the same host. Not managed/RDS.
- CI: GitHub Actions on GitHub-hosted runners: Backend CI (backend tests, API contract, quality
  gates, security hygiene, release metadata), the CodeAgent contract gate with its daily
  re-validation, and a Docs check. A pull request that changes only Markdown or `docs/` gets the
  Docs check and nothing else.

## Application stack

- Backend: FastAPI (Python 3.11), psycopg2 raw-SQL repositories, Alembic. It began as the
  CodeAgent-idiom warehouse-infra skeleton (health/auth/audit + audit_log baseline; the CRM domain
  of the bootstrap seed was stripped). Domain grows via CodeAgent.
- Frontend: framework-free vanilla JS (ApiClient shell) served by nginx, with two pages:
  Dashboards (`app/index.html`) and Studio (`app/studio.html`).
- Auth: **OIDC/Keycloak is provisioned and live** on the persistent stack — `AUTH_MODE=production`
  against the `vtg` realm. The dev-token path (`AUTH_MODE=development` / `AUTH_DEV_TOKEN`) still
  exists for local and CI runs, but is REJECTED at runtime there (a dev token returns 401), so a
  browser login is required to reach live data. The backend is the authority: every `/api` route
  requires authentication except the public ones listed in `backend/app/auth/public_routes.py`,
  and a CI test keeps that list honest. The roles in use are `admin` and `user`.

## Storage / compute posture (decided)

- **PostgreSQL is the storage engine now** — operational store AND warehouse substrate. Decided:
  a dedicated OLAP/column engine is a scale-triggered target, not
  built until dataset scan/aggregate volume demands it. Tracked as its own issue when it does.
- Ingestion/connector runtimes (OData sync, CDC pollers) run as **separate worker services**,
  not the API process — **BUILT**: a `worker` compose service (profile `worker`) running
  `app.worker`'s FOR UPDATE SKIP LOCKED claim loop over the same `execute_run` path. The
  persistent stack runs it (`INGEST_EXECUTOR=worker`); the interim in-API executor
  (`INGEST_EXECUTOR=inline`) remains the compose default.
- Scheduled/recurring triggering is **BUILT for load sequences**: a sequence carries a
  `schedule_cadence` (`hourly`, `daily` or `weekly`) and a `schedule_enabled` switch, the worker
  fires the enabled sequences that are due
  (`app/worker/scheduling.py`, one pending `sequence_runs` row with `triggered_by = 'schedule'`)
  and executes them, running the sequence's pipelines in step order. A single pipeline has no
  schedule of its own: `pipelines.schedule` is stored and has no consumer. The schedule is
  recorded on the sequence run; each pipeline run row still records trigger=manual, including
  the runs a scheduled sequence starts.

## Connectivity & CDC (grown by CodeAgent)

- **OData** is the primary connector; others (direct DB, REST, file/object) follow the source
  abstraction. **OData is provisioned and ingesting**; direct DB, REST and file/object are not
  built yet.
- CDC patterns to support, configured per PIPELINE (`pipelines.cdc_pattern`, one pipeline per
  dataset): receiver-managed delta queue (e.g. SAP ODP/ODQ), pull-based CDC (cursor/watermark),
  snapshot-differencing CDC. Pull-based cursor/watermark CDC is **BUILT and running**
  (`delta_cursors` + `app/ingest/cursor.py` + the OData `$filter` page builder);
  receiver-managed delta queue and snapshot-differencing are NOT built. `pipelines.cdc_pattern` and
  `pipelines.is_enabled` are stored, but no backend code acts on them: every pipeline runs the
  cursor path when triggered, disabled or not.
- Live sources ARE connected. On 2026-11-02 the persistent stack had three OData v4 sources: the
  **public Northwind demo service** (26 datasets), an ERP vendor's demo tenant holding sample
  data (11 datasets) and a feed from a sibling internal application (7 datasets). Together: 44
  discovered datasets, 1,321 discovered fields and about 85,000 ingested records. All 17 pipelines
  use cursor CDC. Three load sequences run them: two scheduled daily, and one whose hourly
  schedule is switched off (`schedule_enabled` is false). No production ERP source is connected
  and none is planned.
- **Outbound OData v4 feed: BUILT.** `/api/feed/v4` exposes ingested datasets to spreadsheet and
  BI clients, authenticated with feed keys (`feed_credentials`), not user tokens.
- Outbound calls go through the egress subsystem (`app/egress/`), which validates each destination
  and is fail-closed. The persistent stack runs `EGRESS_POLICY=strict`.

## Governance status

- **BUILT, core only** (issues closed; `docs/BEHAVIORAL-ARCHITECTURE.md` records what each lacks):
  PII watchdog with reviewer confirm/dismiss (#75); right-to-be-forgotten deletion requests, erasure
  and suppression (#76), API-only, as Studio has no screen for them; retention policies with a
  manual, admin-run purge per policy (#80). There is no scheduled sweep and `anonymize` fails closed.
- PII protection today means flagged values are nulled in field profiles and withheld from charts.
  **The OData feed serves ingested values with no PII check**, and nothing masks by role.
- Audit today is two tables. `audit_log` backs `GET /api/audit` and the Audit history screen, both
  admin-only. `audit_logs` is written by most changes and readable by any signed-in user at
  `/api/audit-logs`.
- **NOT built, tracked and open:** a role catalog with PII-keyed masking (#77), the encryption and
  secrets posture (#78) and structural audit coverage (#79). Do not answer as though they exist.

## Provisioning status

- External connectors: **three OData sources provisioned** (see Connectivity & CDC). ESP: **none
  provisioned**. IdP: **provisioned and live** — Keycloak, `vtg` realm (see Auth above).
- Workflow engine: a **Flowable REST sidecar** is provisioned on the persistent stack as its own
  compose project, not part of this repository's `docker-compose.yml`. The backend reaches it
  through `/api/workflows` and `FLOWABLE_*`, and answers 503 when those are unset. Deploying
  executable process definitions to it is NOT authorized until VTG-DEPLOY-001 is ratified (#290).
- Secrets today: **.env on the host**. A source credential is stored as `secret_ref`, the NAME of
  an environment variable; the value is read from the process environment at call time
  (`app/egress/secrets.py`) and is never stored in the database. A self-hosted secret manager
  (Vault) is the decided target (matching AICRM), not yet provisioned.

## Decided targets (benchmark method, scaled to stage)

- **Backups:** none, by decision. The databases hold disposable test data, so losing them is not
  a crisis; GitHub is the only backing store. Do not design around backup or restore for AIDW.
- **Secret manager:** self-hosted HashiCorp Vault — decided, not yet provisioned.

## Environmental identifiers

- Production domain name: none. AIDW is not deployed to production.
- First source system / OData endpoint to connect: **ASSIGNED** — the public Northwind OData v4
  demo service (see Connectivity & CDC). Production ERP endpoint: none.
