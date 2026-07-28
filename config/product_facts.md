# AIDW Deployment Facts — authoritative answers for factual panel questions

Ground truth for the panel/auto-operator. `[OPERATOR: fill in]` marks unknowns.

## What AIDW is

- An ERP-agnostic, self-hosted data warehouse AND data-governance platform: connect sources
  (OData-first), discover schema, ingest with CDC, profile data and flag PII, enforce retention
  and right-to-be-forgotten erasure, author/generate BPMN processes, and dynamically suggest
  dashboard items — with an embedded AI assistant surface. See product_vision.md.

## Hosting & infrastructure

- **Self-hosted, on-premises** — co-located with the AICRM instance on a private-network host,
  but a **separate workspace and separate repo** (`vtggit/AIDW`). Do NOT assume OS-level
  isolation between the co-located products when reasoning about secret custody or blast
  radius — the deployment does not provide it.
- **This repository is PUBLIC.** Never write host addresses, credentials, customer names or
  internal strategy into tracked files; internal working docs are gitignored at the repo root.
- Orchestration: **docker-compose**. No Kubernetes/ECS.
- PostgreSQL: a **Docker container (postgres:15)** on the same host. Not managed/RDS.
- CI: GitHub Actions (the CodeAgent gate + backend CI the skeleton was bootstrapped with).

## Application stack

- Backend: FastAPI (Python 3.11), psycopg2 raw-SQL repositories, Alembic — the CodeAgent-idiom
  warehouse-infra skeleton (health/auth/audit + audit_log baseline; the CRM domain of the
  bootstrap seed was stripped). Domain grows via CodeAgent.
- Frontend: framework-free vanilla JS (ApiClient shell; dashboard items render here).
- Auth: **OIDC/Keycloak is provisioned and live** on the persistent stack — `AUTH_MODE=production`
  against the `vtg` realm. The dev-token path (`AUTH_MODE=development` / `AUTH_DEV_TOKEN`) still
  exists for local and CI runs, but is REJECTED at runtime there (a dev token returns 401), so a
  browser login is required to reach live data.

## Storage / compute posture (decided)

- **PostgreSQL is the storage engine now** — operational store AND warehouse substrate. Decided:
  a dedicated OLAP/column engine is a scale-triggered target, not
  built until dataset scan/aggregate volume demands it. Tracked as its own issue when it does.
- Ingestion/connector runtimes (OData sync, CDC pollers) run as **separate worker services**,
  not the API process — **BUILT**: a `worker` compose service (profile `worker`) running
  `app.worker`'s FOR UPDATE SKIP LOCKED claim loop over the same `execute_run` path. The
  persistent stack currently runs the interim in-API executor (`INGEST_EXECUTOR=inline`) —
  that is configuration, not missing code. Scheduled/recurring triggering is NOT built
  (`pipelines.schedule` has no consumer; every run is trigger=manual).

## Connectivity & CDC (grown by CodeAgent)

- **OData** is the primary connector; others (direct DB, REST, file/object) follow the source
  abstraction. **OData is provisioned and ingesting**; direct DB, REST and file/object are not
  built yet.
- CDC patterns to support, configured per PIPELINE (`pipelines.cdc_pattern`, one pipeline per
  dataset): receiver-managed delta queue (e.g. SAP ODP/ODQ), pull-based CDC (cursor/watermark),
  snapshot-differencing CDC. Pull-based cursor/watermark CDC is **BUILT and running**
  (`delta_cursors` + `app/ingest/cursor.py` + the OData `$filter` page builder);
  receiver-managed delta queue and snapshot-differencing are NOT built.
- A live source IS connected: the **public Northwind OData v4 demo service** — 26 discovered
  datasets, 182 discovered fields, 828 ingested records, 6 succeeded runs. No production ERP
  source is connected: [OPERATOR: fill in — first production ERP/OData endpoint, if any].

## Provisioning status

- External connectors: **one OData source provisioned** (see Connectivity & CDC). ESP: **none
  provisioned**. IdP: **provisioned and live** — Keycloak, `vtg` realm (see Auth above).
- Secrets today: **.env on the host**. Source credentials (OData/DB/API auth) will need a secret
  manager — self-hosted Vault is the decided target (matching AICRM), not yet provisioned.

## Decided targets (benchmark method — frontier data-platform parity, scaled to stage)

- **Backups:** nightly pg_dump + WAL archiving (PITR) with tested restores — decided, not yet
  provisioned.
- **Secret manager:** self-hosted HashiCorp Vault — decided, not yet provisioned.

## Environmental identifiers pending operator assignment

- Production domain name: [OPERATOR: fill in]
- First source system / OData endpoint to connect: **ASSIGNED** — the public Northwind OData v4
  demo service (see Connectivity & CDC). A production ERP endpoint remains [OPERATOR: fill in].
