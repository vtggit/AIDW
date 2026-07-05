# AIDW Deployment Facts — authoritative answers for factual panel questions

The operator/auto-operator treats every statement here as GROUND TRUTH when answering panel
questions. Keep it current: a wrong fact here becomes a confidently wrong answer. Lines marked
`[OPERATOR: fill in]` are unknown to the automation.

## Hosting & infrastructure

- Deployment model: **self-hosted, on-premises** (same host as the AICRM instance, 10.1.1.233;
  separate user, separate workspace, separate private repo `vtggit/AIDW`). No public cloud
  provider — cloud-region questions do not apply.
- Orchestration: **plain docker-compose**. No Kubernetes/ECS.
- PostgreSQL: a **Docker container (postgres:15) via docker-compose on the same host**. Not
  managed/RDS.
- CI: GitHub Actions (the same CodeAgent gate + backend CI the skeleton was bootstrapped with).

## Application stack

- Backend: FastAPI (Python 3.11), psycopg2 raw-SQL repositories, Alembic migrations — the
  CodeAgent-idiom skeleton (bootstrapped from the AICRM structure; see README).
- Frontend: framework-free vanilla JS (ApiClient + per-entity data sources).
- Auth today: AUTH_MODE=development with AUTH_DEV_TOKEN; no IdP/OIDC provisioned yet.

## Provisioning status

- Warehouse domain (sources/datasets/pipelines/runs) is GREENFIELD — grown by CodeAgent from
  the seed skeleton, not yet built.
- External ingestion connectors / ESP / IdP: **none provisioned**.
- Secrets today: **.env files on the host** (a secret manager is a decided-but-unprovisioned
  target — self-hosted Vault, matching the AICRM decision).

## Decided targets (benchmark method: frontier data-platform parity, scaled to stage)

- **Query/compute:** direct Postgres now; a dedicated OLAP engine is a decided-later target when
  dataset scale demands it (tracked as its own issue when it does).
- **Backups:** nightly pg_dump + WAL archiving (PITR) with tested restores — DECIDED TARGET, not
  yet provisioned.

## Environmental identifiers pending operator assignment

- Production domain name: [OPERATOR: fill in]
