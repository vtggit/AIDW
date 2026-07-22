# AIDW Product Vision — operator steering for panel answers

## North star

AIDW (AI Data Warehouse) is an **ERP-agnostic**, self-hosted, AI-operated data warehouse. It
connects to enterprise source systems, discovers their tables and fields, ingests their data
with change tracking, and **dynamically suggests original dashboard items** from the discovered
schema. It is built and operated by its own CodeAgent instance. Answer every design question
toward **enterprise data-platform capability**: connectivity breadth, schema-driven automation,
lineage, governance, and API-contract discipline — delivered incrementally.

## What AIDW is (the domain, in priority order)

1. **Connectivity — ERP-agnostic, OData-first.** Sources connect via multiple protocols, but
   **OData is the primary and most important** (SAP and most enterprise ERPs expose OData
   services). Other connectors (direct DB, REST/API, file/object-store) follow the same source
   abstraction. A `source` is a configured connection: connector type + endpoint + auth.
2. **Schema discovery.** AIDW queries a connected source for its **available tables and fields**
   (OData `$metadata`, DB information_schema, etc.) and stores that discovered structure with
   lineage.
3. **Change data capture (CDC) / ingestion.** Data is pulled with change tracking. Support the
   three patterns explicitly:
   - **receiver-managed delta queue** (the source/ERP maintains a delta queue the receiver
     drains — e.g. SAP ODP/ODQ),
   - **pull-based CDC** (AIDW polls using a cursor/watermark — timestamp or change-token),
   - **snapshot-differencing CDC** (periodic full snapshot diffed against the prior to derive
     changes when the source offers no native delta).
   The chosen pattern is per-source configuration; the ingestion engine is pattern-pluggable.
4. **Dynamic dashboard suggestion.** From the discovered schema + profiled data, AIDW
   **suggests original dashboard items** (charts, KPIs, tables) automatically, which the user
   accepts/edits. This schema-to-insight automation is a core differentiator.

## Domain vocabulary (prefer these nouns)

`sources` (configured connections to ERP/source systems) · `connectors` (protocol adapters:
odata, db, rest, file) · `datasets`/`tables`/`fields` (discovered + modeled structure with
lineage) · `pipelines`/`runs` (ingestion jobs + executions) · `delta_cursors`/`delta_queues`
(CDC state per source) · `dashboards`/`dashboard_items` (suggested + user-curated).

## Standing engineering decisions (answer consistently — the skeleton was built this way)

- **Audit everything that changes state** (append-only audit_log, old/new/source/actor, PII
  minimized).
- **Schema style:** normalized relational tables with FK constraints — never embedded JSONB for
  domain state; satellite tables over column sprawl. Flat v1 API surfaces over normalized
  storage. (Discovered-schema metadata and CDC state are first-class relational tables.)
- **Pagination contract:** offset — limit default 20, cap 100, non-negative validation (422),
  X-Total-Count, bare-array responses; envelope deferred to v2.
- **Errors:** duplicates → 409 (central UniqueViolation handler); bad references → 422 (FK
  handler).
- **Soft-delete:** deleted_at; list/get exclude by default; include_deleted opt-in.
- **Migrations:** Alembic head-chained, revision ids ≤ 32 chars, succeed on dirty data.
- **Storage engine:** **PostgreSQL now** (the operational + warehouse substrate; recipes speak
  it). Answer per-scale questions with the benchmark method: a dedicated OLAP/column engine
  is a DECIDED-LATER, scale-triggered target — recorded as its own
  issue when dataset scan/aggregate volume demands it; nothing in today's shape blocks that
  migration. Heavy connector/ingestion runtimes (e.g. an OData sync worker) are separate
  services, not in the API process.
- **Auth:** AUTH_MODE=development / AUTH_DEV_TOKEN untouchable; new auth as coexisting modes;
  admin-only management; reuse the role model.
- **Multi-tenancy kept OPEN, not built:** tenant-global now; shape must not block a later
  tenant_id migration.
- **Secrets:** source credentials (OData/DB/API auth) are sensitive — never in audit details,
  never in logs; a self-hosted secret manager is the decided target (see product_facts).
- **Frontend:** framework-free vanilla JS; dashboard items render there.

## The benchmark method (operator-set policy)

Questions with no recorded fact/decision are answered by benchmark — **what would a mature
enterprise data platform do**, judged on capability (connectivity breadth, change tracking,
lineage, governance, API-contract discipline) rather than on any particular vendor's feature
list — scaled to our stage, stated as the DECIDED TARGET (name the tracking issue if infra
doesn't exist yet).
Only environmental identifiers (a domain, a purchased credential) are irreducibly
operator-assigned.

## Hard boundaries

- Draft-only PRs; every merge requires explicit per-PR human authorization.
- Governance blockers respected, not argued away.
- No production data destruction; migrations succeed on existing (dirty) data.
- Never exfiltrate source data or credentials to third parties.
