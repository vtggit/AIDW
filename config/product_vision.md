# AIDW Product Vision — operator steering for panel answers

## North star

AIDW (AI Data Warehouse) is a self-hosted, AI-operated data warehouse: ingest sources, model
datasets, run pipelines, and expose governed, queryable data. It is built and operated by its
own CodeAgent instance. Answer every design question toward **enterprise data-platform
capability**: lineage, governance, reproducibility, and API-contract discipline — delivered
incrementally, never speculatively.

## Standing engineering decisions (answer consistently with these)

These match the CodeAgent-idiom skeleton this repo was bootstrapped from, so generated code fits:

- **Audit everything that changes state.** Append-only audit events with old/new values,
  source, and actor; PII/secret values minimized in audit details.
- **Schema style:** normalized relational tables with FK constraints — never embedded JSONB for
  domain state. Satellite tables over column sprawl when future expansion is named. Flat v1 API
  surfaces over normalized storage.
- **Pagination contract (product-wide):** offset pagination — limit default 20, hard cap 100,
  non-negative validation (422), X-Total-Count header, bare-array responses. New list endpoints
  follow it exactly. Response envelopes deferred to the API-versioning epic (v2).
- **Errors:** duplicates → 409 via the central UniqueViolation handler; bad references → 422 via
  the FK handler; both name the offending value from driver diagnostics.
- **Soft-delete semantics:** deleted_at timestamps; list/get exclude by default;
  include_deleted is an explicit opt-in parameter.
- **Migrations:** Alembic head-chained, revision ids ≤ 32 chars, must succeed on existing
  (dirty) data.
- **Auth:** AUTH_MODE=development with AUTH_DEV_TOKEN is untouchable (the test suite depends on
  it). New auth arrives as coexisting modes. Admin-only management endpoints; reuse the role
  model.
- **Multi-tenancy is kept OPEN, not built:** answer per-tenant questions with "tenant-global
  now; the schema/index shape must not block a later tenant_id migration."
- **Scale posture:** early-stage — synchronous COUNT(*) and direct DB lookups are fine; caching
  (Redis) is a recorded scale trigger, not built now.
- **Frontend:** framework-free vanilla JS (ApiClient + per-entity data sources + views); no SPA
  framework, no query/cache libraries.
- **Breaking changes land once, atomically**, frontend updated in the same PR, called out
  explicitly.

## Domain vocabulary (AIDW-specific)

Core entities the warehouse will grow: **sources** (upstream systems), **datasets** (modeled
tables), **pipelines** (transform jobs), **runs** (pipeline executions), **schemas/columns**
(structure + lineage). Prefer these nouns when the panel proposes entities.

## The benchmark method (operator-set policy)

When a question has no recorded fact and no standing decision, answer by benchmark — **what
would a frontier data platform (Snowflake, Databricks, BigQuery) do**, scaled to our stage —
then state it as the DECIDED TARGET. A benchmark answer is a DECISION, not a provisioned fact
(name the tracking issue if infra doesn't exist yet). Only environmental identifiers (a domain
name, a purchased credential) are irreducibly operator-assigned.

## Hard boundaries

- Draft-only PRs; every merge requires explicit per-PR human authorization.
- Governance blockers are respected, not argued away — a blocked contract goes to a human.
- No production data destruction; migrations must succeed on existing (dirty) data.
