# AIDW Deployment Facts — authoritative answers for factual panel questions

Ground truth for the panel/auto-operator. `[OPERATOR: fill in]` marks unknowns.

## What AIDW is

- An ERP-agnostic, self-hosted data warehouse: connect sources (OData-first), discover schema,
  ingest with CDC, and dynamically suggest dashboard items. See product_vision.md.

## Hosting & infrastructure

- **Self-hosted, on-premises** — same host as the AICRM instance (10.1.1.233), but a **separate
  user, separate workspace, separate private repo** (`vtggit/AIDW`).
- Orchestration: **docker-compose**. No Kubernetes/ECS.
- PostgreSQL: a **Docker container (postgres:15)** on the same host. Not managed/RDS.
- CI: GitHub Actions (the CodeAgent gate + backend CI the skeleton was bootstrapped with).

## Application stack

- Backend: FastAPI (Python 3.11), psycopg2 raw-SQL repositories, Alembic — the CodeAgent-idiom
  warehouse-infra skeleton (health/auth/audit + audit_log baseline; the CRM domain of the
  bootstrap seed was stripped). Domain grows via CodeAgent.
- Frontend: framework-free vanilla JS (ApiClient shell; dashboard items render here).
- Auth today: AUTH_MODE=development / AUTH_DEV_TOKEN; no IdP/OIDC provisioned.

## Storage / compute posture (decided)

- **PostgreSQL is the storage engine now** — operational store AND warehouse substrate. Decided:
  a dedicated OLAP/column engine (ClickHouse/DuckDB/Snowflake) is a scale-triggered target, not
  built until dataset scan/aggregate volume demands it. Tracked as its own issue when it does.
- Ingestion/connector runtimes (OData sync, CDC pollers) will be **separate worker services**,
  not the API process — decided target, not yet built.

## Connectivity & CDC (greenfield — grown by CodeAgent)

- **OData** is the primary connector; others (direct DB, REST, file/object) follow the source
  abstraction. NONE provisioned yet.
- CDC patterns to support per-source: receiver-managed delta queue (e.g. SAP ODP/ODQ),
  pull-based CDC (cursor/watermark), snapshot-differencing CDC. NONE built yet.
- No live source system is connected yet: [OPERATOR: fill in — first ERP/OData endpoint to
  connect, if any].

## Provisioning status

- External connectors / ESP / IdP: **none provisioned**.
- Secrets today: **.env on the host**. Source credentials (OData/DB/API auth) will need a secret
  manager — self-hosted Vault is the decided target (matching AICRM), not yet provisioned.

## Decided targets (benchmark method — frontier data-platform parity, scaled to stage)

- **Backups:** nightly pg_dump + WAL archiving (PITR) with tested restores — decided, not yet
  provisioned.
- **Secret manager:** self-hosted HashiCorp Vault — decided, not yet provisioned.

## Environmental identifiers pending operator assignment

- Production domain name: [OPERATOR: fill in]
- First source system / OData endpoint to connect: [OPERATOR: fill in]
