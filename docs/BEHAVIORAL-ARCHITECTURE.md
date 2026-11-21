# AIDW Behavioral-Layer Architecture

Status: **design of record, verified; partly built** ([what exists today](#implementation-status-checked-2026-11-02-commit-c142baa)) · Owner: CodeAgent (AIDW instance) · Supersedes: ad-hoc entity work

This is the target architecture for AIDW's behavioral layer — the vision's substance beyond the
CRUD scaffold that was all `main` held when this was written in July 2026 (`sources → datasets →
discovered_fields`). Much of it has since been built; the status section below says what. It was
produced by a multi-agent design workflow (3 independent proposals → judge-panel synthesis) and
then **adversarially verified** across four lenses. Constraint-fidelity held; the buildability,
vision-completeness, and risk lenses surfaced defects in the *backlog* that are corrected here
(see [§7 Verification corrections](#7-verification-corrections-applied)).

The four capabilities, in vision priority: **connectivity (OData-first) → schema discovery →
CDC ingestion → dynamic dashboard suggestion.**

---

## Implementation status (checked 2026-11-02, commit c142baa)

The rest of this document is the design of record: the target, the reasoning and the verification
history as written in July 2026. It does not describe the running product. Where it differs from
the code, the code and this table win. Notes marked **Built differently**, **Not built** or
**Current state** in later sections were added in this check; text without a note was left as
written, so "today" there means July 2026.

Schema: 105 migrations, head `0105_add_feed_cred_last_used`, 35 application tables. Only the
`cursor` CDC pattern runs.

| Item | Status | Code, and what is missing |
|---|---|---|
| M0 de-risk | Built | `backend/app/discovery/schema_reader.py`, `backend/app/worker/`, `backend/app/egress/secrets.py`. Parser tests use one small inline V4 EDMX, and the 0b live probe is not in the repo's tests |
| M1 connectivity config | Partly built | `source_connections`, `source_credentials`, `odata_service_configs`. No `sources.is_enabled` or `sources.last_test_status` |
| M2 test one connection | Built | `POST /api/connection-tests/{id}/run` in `backend/app/api/connection_tests.py`, not `POST /api/sources/{id}/test` |
| M3 discover schema | Partly built | `backend/app/discovery/service.py`. No `discovery_runs` rows, tombstones or lifecycle columns |
| M4 cursor ingest | Built | `backend/app/ingest/`, `POST /api/pipelines/{id}/runs` |
| M5 profile, suggest, accept, render | Built | `backend/app/profiling/`, `backend/app/suggestion/`, `backend/app/dashboard/`, `app/js/warehouse.js` |
| M6 real runtime | Partly built | Worker runs ingest, erasure and scheduled sequences (`backend/app/worker/loop.py`). Landing is one JSONB table, `ingested_payloads`, not typed tables. No Vault; test, discover and on-demand profile stay in the API |
| M7 breadth | Not built | `backend/app/egress/http.py` does Basic auth only. No OAuth, mTLS, delta queue, snapshot diff, `information_schema` reader, `run_id` FKs or LLM tier |
| M8 governance | Partly built | The six pillars below |
| #75 PII watchdog (issue closed) | Partly built | `backend/app/pii/`, `backend/app/api/pii_decisions.py`. Core shipped. No unique index on `(dataset_id, fingerprint)`; generic `PUT` can still set `status` |
| #76 RTBF (issue closed) | Partly built | `backend/app/governance/`, `backend/app/worker/loop.py`. Core shipped. No guard on `PUT`/`DELETE` of finished requests, no `needs_attention` filter, `name` not overwritten |
| #77 RBAC and masking (issue open) | Not built | `backend/app/auth/authorization.py` has `admin` and `user` only. No `steward`, `pii_reader`, `pii_status` or masking engine |
| #78 encryption (issue open) | Partly built | `backend/app/egress/http.py`, `backend/app/egress/policy.py`; backend port on loopback by default. No TLS in the repo, `verify_tls` unread, no `DB_SSLMODE`. LUKS and backups are operator work and cannot be checked from code |
| #79 audit (issue open) | Partly built | `backend/app/audit/recorder.py` writes `audit_logs`; PII writes `audit_log`. No middleware, read auditing, tamper trigger or purge function |
| #80 retention (issue closed) | Partly built | `backend/app/retention/`, `POST /api/retention-policies/{id}/sweep`. Manual purge only. No `anonymize`, scheduled sweep, seeded defaults or audit rows |

Shipped outside this design: the OData v4 feed with feed keys (`backend/app/api/feed_odata.py`,
`backend/app/feed/`), load sequences with the worker's scheduler
(`backend/app/api/load_sequences.py`, `backend/app/worker/scheduling.py`), process definitions with
the BPMN generator (`backend/app/bpmn/`), dashboard layouts (`dashboard_item_layouts`) and an
optional Flowable proxy (`backend/app/api/workflows.py`).

---

## 1. Runtime topology

Two runtimes, one Postgres, one secret seam:

- **API process** (existing FastAPI + Alembic + Postgres) — owns *all* metadata/state CRUD, all
  reads, and *thin behavioral seams* that either **enqueue** work (insert a `queued`/`pending`
  row) or run **pure in-DB logic** over already-persisted rows (accept a suggestion; run the
  suggestion rule engine over stored profiles). **Zero source egress; never touches raw secrets.**
  **Built differently:** the API still reaches sources. In the default `INGEST_EXECUTOR=inline`
  mode it runs ingest itself; discovery, on-demand profiling and chart data have no worker path.
  `POST /api/connection-tests/{id}/run` and `POST /api/sequence-runs/{id}/execute` reach the
  source with no `ENABLE_INAPI_EGRESS` check at all.
- **Connector/ingestion worker** — ONE shared service (operator-provisioned; see §5). Owns *all*
  egress and heavy I/O: OData `$metadata` GET, DB `information_schema`, CDC drain/poll/diff, row
  landing, profiling scans. Claims work via `SELECT … FOR UPDATE SKIP LOCKED`, resolves
  `secret_ref` at connect time, writes results + status in one transaction.
  **Built differently:** the worker is in this repo (`backend/app/worker/`, opt-in compose profile
  `worker`). It claims `runs`, `deletion_requests` and scheduled `sequence_runs`, so its egress is
  ingest and the profiling pass that follows. `information_schema` discovery and drain/diff CDC
  are not built.
- **One job substrate (decided once):** every behavioral trigger is a DB work-table row in a
  `queued`/`pending` state the worker drains via skip-locked polling — `connection_tests`,
  `discovery_runs`, and `runs` alike. A real broker (Redis/LISTEN-NOTIFY) is a later
  scale-triggered issue.
  **Built differently:** connection tests, discovery and retention sweeps run synchronously in the
  request; only the three spines above are drained.
- **Secret boundary (one rule):** credentials live ONLY as `secret_ref` (opaque path) +
  non-secret `principal`. The namespace is **`aidw/sources/<id>/<key>` from day one.** An interim
  env/file resolver (secrets are `.env` on the host today) satisfies it now; **Vault later is a
  resolver-internal swap, not a schema or API change.** No secret material ever lands in a DB
  column, `audit.details`, an `error`/`message` field, or a log line.
  **Built differently:** `secret_ref` is the name of an environment variable
  (`^[A-Z][A-Z0-9_]{2,63}$`), and `backend/app/egress/secrets.py` reads only the environment. There
  is no `aidw/sources/…` namespace, file resolver or Vault.
- **Interim in-API egress (`ENABLE_INAPI_EGRESS`, default OFF):** a flag-gated synchronous in-API
  path runs the OData fetch inline for **anonymous / basic-auth-only** sources (short timeout, no
  cert material), writing the *same* `connection_tests`/`discovery_runs`/`runs` rows the worker
  later will. This makes the vertical slice demoable **before** the worker/Vault exist; the worker
  later assumes those identical rows unchanged, so nothing is thrown away.

---

## 2. Two settled reconciliations

1. **`sources` extension — satellites win.** Connectivity's satellite tables
   (`source_connections`, `source_credentials`, `odata_service_configs`) are the target. The
   flat `endpoint_url`/`auth_mode`/`secret_ref`-on-`sources` alternative is dropped to avoid a
   build-then-migrate. `sources` itself gains only `is_enabled` + `last_test_status`.
   **Not built:** neither column exists; `sources` is still `id`, `name`, `type` and timestamps.
2. **Two run spines, kept separate.** `discovery_runs` (discovery) and `runs` (ingestion) have
   different shapes/lifecycles. `field_profiles`/`suggestions` get a `run_id` FK only in breadth,
   once `runs` is on `main` — the *only* cross-capability FK edge in the whole plan.
   **Current state:** `runs` is on `main`, but those FKs were not added. `discovery_runs` exists
   with generic CRUD only; `POST /api/sources/{id}/discover` writes no row to it.

---

## 3. Data model — 18 tables (2 extended + 16 new)

**Current state:** the count above is the July 2026 design of the first slice, not today's schema,
which has 35 application tables. The diagram below draws 19 tables; 18 of them exist, and
`delta_queues` was not built. The other 17 are the audit, governance, process, sequence, feed,
layout and landing tables listed by the migrations.

```
sources (MAIN; +is_enabled, +last_test_status)
 ├─ source_connections    (endpoint, protocol_version, timeout_seconds, verify_tls)         [CONN]
 ├─ source_credentials    (auth_scheme, principal, secret_ref, token_endpoint)              [CONN]
 ├─ odata_service_configs (metadata_path, default_entity_set, supports_delta)               [CONN]
 ├─ connection_tests      (status, message, latency_ms, tested_at)                          [CONN]
 └─ discovery_runs        (status, trigger, started/finished_at, counts, error_summary)     [DISCOVERY]

datasets (MAIN)          +source_object_name, +lifecycle_status, +first/last_seen_run_id     [DISCOVERY]
 └─ discovered_fields (MAIN) +source_field_name, +is_nullable, +is_key, +ordinal,
                              +lifecycle_status, +first/last_seen_run_id                      [DISCOVERY]
     └─ field_profiles    (row/null/distinct_count, min/max/mean/stddev, most_common_value)  [DASHBOARD]

pipelines (name, cdc_pattern, schedule, enabled)                                             [CDC]
 └─ runs (status, trigger, timing, rows_read/written, error_detail)                          [CDC]
     ├─ delta_cursors  (cursor_value, cursor_kind)                                           [CDC]
     ├─ delta_queues   (subscription_handle, ack_pointer, queue_status)                      [CDC — breadth]
     └─ ingested_records (business_key, op, ingested_at)                                     [CDC]

dashboards (name, description)                                                               [DASHBOARD]
 └─ dashboard_items (title, item_type, aggregation, position)                                [DASHBOARD]
     └─ dashboard_item_fields (field_role)                                                   [DASHBOARD]
suggestions (title, item_type, aggregation, score, rationale, strategy, status)              [DASHBOARD]
 └─ suggestion_fields (field_role)                                                           [DASHBOARD]
```

**Built differently:** `discovered_fields.ordinal` is `field_position`, and `pipelines.enabled` is
`is_enabled`. Not built: `sources.is_enabled`, `sources.last_test_status`,
`datasets.source_object_name`, `discovered_fields.source_field_name`, `lifecycle_status` on both
tables, `field_profiles` mean and stddev, and the `discovery_runs` timing, count and error columns.
`pipelines.cdc_pattern`, `.schedule` and `.is_enabled` are stored, but no backend code acts on them,
so every pipeline runs the cursor path when triggered.

**FK edges** (all nullable `VARCHAR(64)`, `ON DELETE SET NULL`, indexed): the satellite/child
tables → their parent (`source_id`, `dataset_id`, `pipeline_id`, `discovered_field_id`,
`dashboard_id`, `suggestion_id`, etc.); `datasets`/`discovered_fields.first|last_seen_run_id →
discovery_runs`; `delta_cursors.cursor_field_id → discovered_fields`, `.last_run_id → runs`;
`ingested_records.run_id → runs`, `.dataset_id → datasets`; `dashboard_items.source_suggestion_id
→ suggestions`; `field_profiles.run_id`/`suggestions.run_id → runs` (breadth only).

Every new table follows the standing contract: `VARCHAR(64)` string PK; audit + soft-delete
(`deleted_at`, excluded by default); offset pagination (limit 20, cap 100, 422 on bad input,
`X-Total-Count`, bare-array v1); 409 on duplicate, 422 on bad FK; Alembic head-chained revisions
≤32 chars that succeed on dirty data.

**Current state:** the string PKs, the 409 and 422 handling and the revision rules hold. No table
has `deleted_at`, and repositories hard-delete. Most list endpoints are unpaginated full-table
reads; only `GET /api/load-sequences` and `GET /api/sequence-runs` take `limit`/`offset` and emit
`X-Total-Count`, with no default limit. Audit writes cover some tables, not all (see #79).

**Landing = PostgreSQL now** — one typed table per dataset (schema-on-write, columns mirror
`discovered_fields`), managed by the worker at ingest, reachable only through the
pipeline/dataset indirection so a later OLAP-engine swap is a localized worker+landing change,
never an API rewrite. `ingested_records` is the substrate-agnostic CDC op-log (business_key + op
+ provenance) so delete/lineage/idempotent-replay semantics are representable independent of the
typed table.

**Built differently:** landing is one shared table, `ingested_payloads` (migration 0075): the raw
source row as JSONB, unique on `(dataset_id, business_key)`, with no typed columns or per-dataset
DDL. `apply_rows` (`backend/app/ingest/cursor.py`) writes it in both executor modes, and chart
aggregation and the OData feed read it directly by `dataset_id`.

---

## 4. Build approach & lane discipline

CodeAgent ships **draft PRs to the AIDW API repo**; a running process is not a PR. Lanes:
`[E]` entity · `[F+]` field-add · `[FF]` freeform · `[MI]` manual-infra (operator).

Rules (several are corrections from the verify — see §7):

- **One column per `[F+]`.** The field-add lane adds exactly ONE column per AC/PR. A table needing
  N FK/scalar columns is N field-add PRs, each in the proven phrasing: *"Add a nullable `<col>`
  field (VARCHAR 64) to the `<table>` table, referencing `<ref>(id)` with ON DELETE SET NULL, and
  an index."*
- **FK field-adds depend on the ref table being MERGED** (not merely authored) — its migration
  must be on `main` before the FK builds, or the lane fail-closes on "unknown table."
- **Frontend uses the deterministic frontend lane** per read-model (one data-source + render AC
  each), proven via Playwright. Reserve `[FF]` only for small bespoke pieces (SVG chart renderer,
  accept/dismiss wiring), each its own `<8-file` AC.
- **Freeform is small & single-purpose** — a parser, a reconciler, one endpoint, one CDC pattern.
  Never a large multi-file reconstruction (freeform's hard caps: MAX_FILES 8, ~64k chars, refuses
  shrinking an existing module below 50%). A non-converging freeform trial opens **no PR** (worst
  case = spent tokens).
- **Any code that lands outside the API repo is `[MI]`, never `[FF]`** (the worker, Vault, cert
  storage, OLAP). **Built differently:** the worker's code landed inside this repo.
- **Every freeform behavioral module must assert on OBSERVABLE OUTPUT STATE** (rows actually
  landed / cursor actually advanced / a suggestion actually references real field ids) — not
  merely a 200/handler-ran assertion — so a gamed proof cannot pass (the reward-hack guard).

Deterministic entity/field-add PRs (~58% of the slice) batch in parallel and are never the
bottleneck; the critical path is the ~10 freeform + `[MI]` links.

---

## 5. Milestone plan (dependency-ordered)

**Milestone 0 — de-risk the existential unknowns first** (parallel; depend only on `main`):
1. `[FF]` OData `$metadata` (EDMX/CSDL **V2 + V4**) parser module — pure XML→normalized-list, AC-tested vs checked-in real V2/V4 fixtures with exact counts (probe R3).
2. `[MI]` **Skeleton worker** — polls a `pending` row, flips status, writes latency; proves substrate + `SKIP LOCKED` claim + writeback before any connector logic (probe R1).
3. `[MI]` **Interim env/file secret resolver** on `aidw/sources/<id>/<key>` (probe R2). **Built differently:** `backend/app/egress/secrets.py`, environment variables only (see §1).
- **0b (critical, from verify): live-OData fidelity probe** — point the `ENABLE_INAPI_EGRESS` path at ONE real public OData service (SAP ES5 / TripPin / Northwind V2+V4) and run parser(#1)+reconciler(#18) against its **live `$metadata` + one real data page**, asserting exact entity-set/field counts + one full discover→ingest cycle. Retires the load-bearing risk before any infra is built; costs only tokens on failure. Fixture tests stay as the CI net.

**Milestone 1 — connectivity config:** `[E]` `source_connection`, `source_credential`,
`odata_service_config` (+ each `source_id` FK as its own `[F+]`); `[F+]` `sources.is_enabled`,
`[F+]` `sources.last_test_status`.

**Milestone 2 — test one connection** 🟢 *first thin API⊥worker proof:* `[E]` `connection_test`
+ `[F+]` `source_id`; `[FF]` `POST /api/sources/{id}/test` (enqueue + interim exec:
anonymous/basic OData root GET, record status/latency/sanitized message).
**Built differently:** the route is `POST /api/connection-tests/{id}/run`. It fetches `$metadata`
synchronously, with no `ENABLE_INAPI_EGRESS` check.

**Milestone 3 — discover schema:** `[E]` `discovery_run` + `[F+]` `source_id`; the `datasets`
(4) and `discovered_fields` (7) discovery columns **as individual `[F+]` PRs**, the two
`first/last_seen_run_id` FKs each ordered **after `discovery_run` is merged**; `[FF]`
reconciliation module (UPSERT + tombstone, idempotent, 5 named test cases); `[FF]`
`POST /api/sources/{id}/discover`. **Schema-tier suggestions fire here** (see §6).
**Built differently:** discovery upserts and never tombstones, so a field that disappears upstream
keeps its row. It writes no `discovery_runs` row, so `first_seen_run_id` and `last_seen_run_id`
are set only through generic CRUD. The endpoint takes an optional `entity_sets` allowlist.

**Milestone 4 — ingest one dataset (cursor pattern):** `[E]` `pipeline`, `run`, `delta_cursor`,
`ingested_record` (+ each FK as its own `[F+]`); `[FF]` `POST /api/pipelines/{id}/runs`
(enqueue); `[FF]` cursor-ingest **split into small modules** — (a) OData-page→rows mapper, (b)
cursor-advance + run-count transaction over fetched rows, (c) `$filter` URL builder from a
watermark — composed in a thin endpoint, each fixture-tested, no network.

**Milestone 5 — profile + suggest + accept + render** 🎯 *(closes the slice):* `[E]`
`field_profile`, `suggestion`, `suggestion_field`, `dashboard`, `dashboard_item`,
`dashboard_item_field` (+ FKs as individual `[F+]`); `[FF]` interim profiling; `[FF]`
**profile-tier** suggestion refinement; `[FF]` accept/dismiss; **deterministic frontend** per
read-model + one small `[FF]` SVG chart renderer, Playwright-driven.

**🎯 At Milestone 5 the thin vertical slice is closed end-to-end** — one anonymous/basic OData
source → test → discover → cursor-ingest → profile → suggest → accept → render — entirely in-API
behind `ENABLE_INAPI_EGRESS`.

**Milestone 6 — onto the real runtime (breadth):** `[MI]` provision Vault (resolver swap);
`[MI]` promote the skeleton worker to the full connector/ingestion worker (migrate `/test`,
`/discover`, cursor-ingest, `/profile` logic out of the API *unchanged*); `[MI]` per-dataset
typed landing tables.
**Built differently:** the worker took cursor-ingest and the profiling pass after it, plus erasure
and scheduled load sequences. Landing is the shared `ingested_payloads` table (§3). Vault is not
provisioned.

**Milestone 7 — breadth:** OAuth client-credentials; x509/mTLS `[MI]`; `delta_queue` +
snapshot-diff CDC strategies (worker-side `[MI]`/`[FF]` split); DB `information_schema` discovery
(reuses reconciler); `run_id` provenance FKs; LLM-narrative suggestion layer (opt-in, worker-side).

**Milestone 8 — governance & compliance:** the six §10 pillars (AIDW issues #75–#80); the M6
landing-table `[MI]` must land compliant with §10's cross-pillar DDL contract.

---

## 6. Delivering the differentiator: automatic suggestion (two tiers)

The vision's differentiator is that AIDW suggests dashboard items **automatically from discovered
schema + profiled data** — it must not be gated behind full ingestion or manual buttons. So:

- **Schema-tier (fires immediately after discovery):** a rule pass over `discovered_fields` alone
  (type / nullability / key / ordinal + any `$metadata` cardinality) emits candidate suggestions
  with a `schema-only` strategy and lower confidence — the instant a schema is discovered, before
  a single row lands.
- **Profile-tier (after ingest):** the `field_profiles`-based rules upgrade scores once rows are
  ingested.
- **Automatic triggers:** on discovery-run success, enqueue/inline a regenerate-suggestions pass;
  on ingest-run success, a profile+regenerate pass. Suggestion no longer hard-depends on ingest.

Rule sketch: categorical low-card → bar/pie; numeric measure + categorical dim → aggregate bar;
temporal + measure → line; single high-fill numeric → KPI; high-card string → table.
`score = fill_rate × cardinality_fit × type_fit`.

**Built differently:** the schema tier emits `kpi`, `bar`, `line` and `table`, never `pie`. The
profile-tier score is not this formula: `backend/app/suggestion/rescore.py` sets fixed bands for a
dimension (0.82 low-arity, 0.12 near-unique, 0.45 otherwise) and lifts a measure's score by its
fill rate. After ingest, suggestions are re-scored, not regenerated.

### Chart data for accepted items (interim in-API egress)

An accepted item renders as a real chart in the warehouse UI via
`GET /api/dashboard-items/{id}/data` (any authenticated user; gated by `ENABLE_INAPI_EGRESS`
like discovery/profiling — 503 when off). When this was designed there was deliberately **no
local row store to query** (typed landing tables are Milestone 6), so the endpoint reuses
profiling's seam:
resolve the item's role-tagged fields to its dataset (field-less row-count KPIs resolve via
`source_suggestion_id -> suggestions.dataset_id`), fetch one sampled page
(`{endpoint}/{set}?$top=200`), aggregate in Python (`count`/`sum`/`avg` grouped by the
`dimension` — or `temporal`, sorted chronologically — field; no dimension = single-point KPI;
`none` = 422 not chartable), and return `series: [{label, value}]` with
`sample_size`/`buckets_total` provenance (top-20 buckets, `truncated` flagged; fetch
failures are logged server-side and surface as a generic 422 — no upstream error text).
When landing tables land, only the row source changes (SQL replaces the live sample).

**Current state:** that swap has happened for items with a dimension. When `ingested_payloads` holds
rows for the dataset, `item_data` (`backend/app/dashboard/data_service.py`) aggregates all of them
in SQL and adds `source: "landed"`, `total_rows` and `refreshed_at`. KPI items and datasets with no
landed rows stay on the live sample. More than the row source changed: `aggregate_series`
(`backend/app/ingest/landing.py`) orders by value even for a temporal dimension, and folds the tail
beyond 20 buckets into an `Other` bucket. The 503 gate also applies to landed charts, which need no
egress. `GET /api/dashboard-items/{id}/series` is a second endpoint with the same governance that
reads the live sample only.

Governance is inherited, not re-invented:
- **PII:** any referenced field with an ACTIVE flag (`flagged` or `confirmed`) withholds the
  whole item (422) — a pending review reads as PII until decided, mirroring profiling's
  detect-before-write withholding.
- **RTBF:** suppressed subjects are dropped from the ENTIRE aggregation — unlike profiling,
  which keeps non-personal counts full-sample, a chart's labels ARE row values, so counts and
  totals exclude erased subjects too. `sample_size` is reported POST-suppression: the erased
  subject is invisible, never visibly redacted (no pre/post pair that would telegraph how many
  rows were erased), and the suppression list is read AFTER the live fetch so an erasure
  committed mid-fetch still applies. Same fail-closed pepper contract as ingest/profiling:
  hashing only runs when the dataset has suppression entries; a missing pepper then raises
  rather than serving the erased subject (`test_dashboard_item_data.py` pins all of this).

The SPA fills each item's chart after the dashboards render (`_fillCharts`), drawing inline
SVG in-house (bar/line/KPI + a value-list fallback; no chart library) with a provenance
footer, and shows the 503/422 reasons as notes instead of charts.

---

## 7. Verification corrections applied

The adversarial pass (constraint-fidelity **held**) forced these fixes into the plan above:

| Lens | Defect caught | Correction |
|---|---|---|
| buildability | Multi-FK items bundled 2–7 columns into one `[F+]` | each column is its own field-add PR (~55 PRs, not ~45) |
| buildability | FKs ordered before their ref table was *merged* | FK `[F+]` depends on the ref table's PR being merged |
| buildability | Frontend slice tagged `[FF]` | deterministic frontend lane per read-model + tiny `[FF]` chart renderer |
| buildability | Cursor-ingest one giant `[FF]` gen | split into mapper / cursor-txn / URL-builder modules |
| buildability | Worker CDC code tagged `[FF]` | worker-repo code is `[MI]`; only the in-API interface/registry is `[FF]`/`[E]` |
| vision | Suggestion gated behind full ingestion + manual buttons | two-tier (schema + profile) + automatic triggers (§6) |
| risk | Freeform validated only vs fixtures | Milestone 0b **live-OData fidelity probe** + assert-on-observable-output-state |

---

## 8. What CodeAgent cannot build (operator manual-infra)

1. The **connector/ingestion worker service** (its *logic* ships as fixture-tested API-repo
   freeform modules — so R3/R4 retire before it exists — but the running process is operator infra).
2. **Secret manager (Vault)** + the least-privilege resolver (namespace fixed → a swap).
3. **Per-dataset typed landing tables** (runtime schema-on-write DDL; permission/migration sign-off).
4. **x509/mTLS** client-cert material storage + worker presentation.
5. The **dedicated OLAP/column engine** (scale-triggered; the landing indirection keeps it local).
6. **Standing up** the job substrate / worker runtime (the *decision* is made here; the deploy is operator).

**Current state:** the worker's code is in this repo and compose can start it (`--profile worker`);
running it remains an operator choice. Items 2, 4 and 5 do not exist. Item 3 was built differently,
with no runtime DDL (see §3).

---

## 9. Risk ledger

| # | Risk | Smallest probe |
|---|---|---|
| R1 | Worker model the PR pipeline can't build (existential) | skeleton worker (M0 #2) |
| R2 | Secret management / Vault unprovisioned (blocking) | interim env/file resolver (M0 #3) + ship `source_credentials` early |
| R3 | OData `$metadata` fidelity V2/V4 + SAP dialect (high) | pure parser vs checked-in real corpora (M0 #1) **+ live-service probe (M0 0b)** |
| R4 | Freeform reliability on real logic (high) | small ascending-difficulty fixture-tested modules; assert observable output state |
| R5 | Landing needs runtime DDL from worker (high) | prove CDC semantics on `ingested_records` op-log first; typed schema-on-write is a gated worker step |
| R6 | Serial FK chain × human merge gate (high) | batch scalar entities + pure modules in parallel; only the 6-link critical path is gated |
| R7 | Connector registry vs enum (moderate, reversible) | interim validated `sources.type` string; registry is a later refactor |
| R8 | Discovery scope + tombstone semantics (moderate, reversible) | discover-all + tombstone (never hard-delete); user allowlist before drift noise |

**Load-bearing insight:** the worker's *code* and *runtime* are decoupled — code ships first as
fixture-tested API-repo modules, so R3/R4 retire before R1's worker is stood up. The critical
path is 6 links (parser → reconciler → worker → CDC strategies → landing → profiling worker);
everything green batches in parallel.

---

## 10. Governance & compliance

Four operator mandates extend the closed slice into a *governed* warehouse: **access control &
anonymization · encryption at rest + in transit · auditability & traceability · automated
retention** — realized as six pillars, adding a **PII watchdog** (classification is the
prerequisite of both masking and anonymization) and **right-to-be-forgotten (RTBF)** erasure.
Each pillar was designed by its own agent and independently **adversarially verified** against
the actual tree (the §7 discipline, applied per pillar); the verification's defect fixes are
normative and already folded into the text below — where a defect contradicted the original
design, the corrected version is what stands. Full provenance — considerations, open questions,
verification verdicts — is preserved as comments on the AIDW issues: **#75** pii-watchdog ·
**#76** rtbf · **#77** rbac-masking · **#78** encryption · **#79** audit-traceability ·
**#80** retention.

**Current state:** "normative" here means normative for the design. #75, #76 and #80 are closed and
#77, #78 and #79 are open, but no pillar is built as written; the status table records what is.

### Auditability & traceability (#79)

**Verified baseline (July 2026):** `audit_log` + `AuditService` exist, but `AuditService.write()`
has ZERO call sites — only `GET /api/audit` (admin, read-only) touches the service; the documented
"Option B: audit failure rolls back the mutation" policy governed nothing then. This pillar makes
auditing *structural* rather than call-site discipline, because nearly every mutation endpoint is
lane-generated CRUD that will never remember to call a service.

**Built differently:** `AuditService.write()` still has no call sites, but audit rows are written,
to two tables. `record_audit` (`backend/app/audit/recorder.py`) inserts into `audit_logs` (migration
0055) on the caller's cursor. The repositories for sources, source connections and credentials,
datasets, pipelines, suggestions, PII flags and retention policies call it, as do the RTBF lifecycle
and executor. PII decisions and retro-scrubs insert into the original `audit_log` directly
(`backend/app/pii/service.py`). `GET /api/audit` and the Audit history screen read `audit_log` only.
`audit_logs` has generic CRUD at `/api/audit-logs`: any authenticated user can read it and an admin
can create, edit or delete rows. Items 1, 2 and 4–8 and the schema deltas below are not built. Item
3 holds in part: bulk writes write no audit rows, but the human trigger is not recorded either.

1. **Mutation auditing is middleware, not call sites.** An `AuditMiddleware` records every 2xx
   `POST/PUT/PATCH/DELETE` under `/api/`: `entity_type` = first path segment, `entity_id` = path
   param or the `id` of a 201 body (response-body buffering required), `action` = method map —
   and, stated generically so the rule survives new endpoints: *a 2xx POST whose trailing path
   segment is a non-parameter literal records `action='trigger:<segment>'`*, pinned in tests
   against the five real trigger endpoints (`discover`, `profile`, `runs`, `accept`, `dismiss`).
   Mechanics that trip lanes are spelled out: `AuditMiddleware` is the FIRST `add_middleware`
   call in `create_app()` — Starlette's last-added-is-outermost — so it sits inside
   `RequestIDMiddleware` and reads a live request-id contextvar; `get_current_user` gains a
   `request: Request` parameter and stashes the resolved user on `request.state`. Lane-generated
   CRUD, current and future, is covered with zero per-endpoint code. (Auth-disabled mode
   synthesizes `roles=[]`, so every mutation 403s — `anonymous` can appear only on `read` rows.)
   `[FF]`
2. **Policy revision: Option B → B′ (fail-loud write-behind).** `get_cursor()` is
   one-connection-one-commit, so the business mutation is committed before middleware runs;
   same-transaction rollback is unimplementable at this altitude without an invasive shared-
   transaction seam in every lane repo. New policy: the audit write happens before the response
   is returned; failure → 500 + ERROR log carrying `request_id`. The commit-then-crash window is
   accepted and documented.
3. **Data plane is run-spine-audited, not row-audited.** Worker bulk writes never write
   `audit_log` rows — `runs`/`discovery_runs` (status, counts, timing, error_detail) ARE their
   audit record; `audit_log` holds the human trigger. Volume stays O(requests), never O(rows).
4. **Read auditing: per-request, path-allowlisted.** Today's real PII read surfaces are
   `field_profiles` (raw sampled min/max/most_common values) and `ingested_records` (verbatim
   business keys). GET/LIST on those paths write one `action='read'` row per request behind
   `AUDIT_READS` (default on) — with the default allowlist spelled as the REAL hyphenated route
   prefixes, `field-profiles,ingested-records`, and a test resolving it against the live app
   routes (the underscore spelling would silently audit nothing — the exact silent divergence
   this pillar exists to prevent). `X-Total-Count` capture is best-effort — no endpoint emits it
   today; the value-bearing list endpoints are unpaginated full-table reads, and
   `GET /api/ingested-records` dumping the whole verbatim op-log is a leak amplifier filed as its
   own follow-up. Per-row read audit is rejected (unbounded volume); flag-aware scoping is a
   deferred refinement on the watchdog's `pii_flags`. Dashboards/suggestions reads
   (aggregates/metadata) are not audited. `[FF]`
   **Current state:** the value-bearing surfaces now also include `ingested_payloads`, read through
   the OData feed, and two list endpoints do emit `X-Total-Count` (see §3).
5. **Governance events are explicit, not inferred.** A small writer module + action vocabulary
   (`pii.flag_set|cleared`, `deletion.requested|approved|executed`, `retention.policy_set|purged`,
   `audit.purged`) with reserved system actors (`system:worker`, `system:retention`, …) — used by
   the PII/RTBF/retention pillars, including worker-side events with no HTTP request. `[FF]`
6. **Tamper posture is a ladder, stated honestly.** (a) Now: `BEFORE UPDATE OR DELETE` trigger on
   `audit_log` raising unless GUC `aidw.allow_audit_purge='on'` (DELETE only; UPDATE always
   blocked) — an in-repo guardrail, NOT a security boundary `[FF]`; (b) next: least-privilege DB
   role (INSERT/SELECT-only on `audit_log`) for API + worker — split per §4 lane discipline into
   an `[FF]` (dual-credential `MIGRATION_DB_USER/_PASSWORD` support in `start.sh` + compose,
   falling back to `DB_USER` so nothing breaks pre-split; migrations run in-container today, so
   this is repo code, not pure operator work) + the `[MI]` (role creation, grants, secret
   wiring); (c) hash-chaining deferred (serialization cost vs marginal gain once roles split).
7. **Audit self-retention runs as `SECURITY DEFINER`.** `AUDIT_RETENTION_DAYS` (default 0 = keep
   forever) drives a purge implemented as a Postgres `SECURITY DEFINER` function
   (`purge_audit_older_than()`, owned by the migration/owner role, GUC/window logic inside;
   `aidw_app` gets EXECUTE only) — a plain app-role DELETE would be permission-denied the moment
   (b)'s role split lands; the two items were mutually inconsistent until the purge moved into
   the function. The purge writes a summary `audit.purged` event — deleting audit history is
   always itself audited. Invoked by the retention pillar's sweep. `[FF]`
8. **details hygiene.** Redacted request payload (denylist: password/token/authorization/
   client_secret; `secret_ref` explicitly allowed — an opaque path per §1), 4 KB cap, response
   bodies never stored. No secret material in `audit_log` — the §1 rule, enforced in one place.

**Schema deltas:** `audit_log.request_id` (+index) `[F+]`* — and the middleware `[FF]` owns the
populator (a `request_id` field on `AuditEvent`, the column in the repository INSERT, pass-through
from `get_request_id()`), ordered after the DDL merge or tolerant of the missing column — the
`[F+]` alone is DDL-only and would ship the column forever-NULL. Query indexes
`(entity_type, timestamp DESC)`, `(entity_id)`, `(actor_sub)` + list-endpoint filters `[FF]`.
*`audit_log` is a non-contract SERIAL table — if the `[F+]` lane fail-closes on it, that is
engine-feature evidence and the column folds into the middleware FF's migration instead.

**Engine candidates:** (a) E-lane mutation tests assert an audit row once the middleware lands
(extends the §4 observable-output-state guard); (b) `[F+]`/`[E]` support for legacy/non-contract
tables (SERIAL PK, no soft-delete).

### PII watchdog (#75)

A deterministic two-tier PII classifier — an exact structural clone of the suggestion engine
(§6): pure rule module + fingerprint reconciler + sticky human decisions + automatic triggers —
emits `pii_flags` over `discovered_fields`, and `field_profiles` **fails closed**: raw example
values are never persisted for a flagged field.

- **Deterministic rules, not NER/LLM.** On-prem, no cloud; classification must be reproducible
  and auditable. Schema-tier = token rules over field name + `data_type` (the `_tokens`
  whole-token splitter discipline from `suggestion/engine.py` — `EmailedCount` ≠ email).
  Profile-tier = format detectors (email / phone / IBAN / Luhn-valid PAN / national-id / IP) over
  the profiling sample **already in memory**. An LLM tier is a later opt-in worker-side layer,
  like M7's narrative tier.
- **Fail-closed suppression, not confidence-gated.** ANY active flag (`flagged`|`confirmed`)
  NULLs `min_value`/`max_value`/`most_common_value` at write time — a false positive costs one
  NULLed example value, a false negative leaks PII at rest; asymmetric, so no threshold.
  Aggregates (`row_count`/`null_count`/`distinct_count`) are retained: statistics, not values —
  `rescore.py` consumes only these, so suggestion scoring is unaffected.
- **Detect-before-write, plus retro-scrub.** Value detectors run over the sample BEFORE the
  profile upsert (zero leak window for new data); a flag INSERT/revive additionally NULLs any
  pre-existing profile row of that field in the same transaction (backfill for pre-watchdog
  rows), emitting an audit event. Scrub/reconciler events carry
  `actor_sub='system:pii-watchdog'` (`actor_roles=[]`); an audit-write failure inside the
  profiling transaction rolls back the whole pass — fail-closed-correct, since the raw values are
  not persisted either. Audit payloads go in `AuditEvent.details` (persisted as `details_json`)
  and carry field ids + counts, NEVER sampled values.
- **Fingerprint = sha256(field_name | category), scoped per dataset** — semantic identity
  excludes confidence/tier/rationale, so profile-tier confirmation UPDATEs the same flag
  (upgrades confidence, sets `detection_tier='profile'`) and a field that tombstones and returns
  under a new id re-binds without losing the human decision. Idempotency gets the DB backstop,
  not just application logic: the suggestions precedent it mirrors *has* one
  (`UNIQUE(dataset_id, fingerprint)`, migration 0025), and three concurrent triggers can race a
  SELECT-then-INSERT into duplicate flags. Until CodeAgent#393's composite-unique grammar lands,
  the unique index ships as a tiny single-purpose `[FF]` migration and the reconciler INSERTs
  `ON CONFLICT (dataset_id, fingerprint) DO NOTHING`; #393 stays the lane-native replacement.
  **Not built:** `pii_flags` has no such unique index, and the reconciler still does a SELECT then a
  plain INSERT, so this race is open.
- **Sticky overrides, tier-scoped staling.** `confirmed`/`dismissed` are human, audited, never
  touched by the reconciler; `dismissed` lifts suppression at the next profile pass. Schema-tier
  flags go `stale` when the rule stops firing or the field vanishes; **profile-tier flags
  ratchet** — a later clean sample proves nothing, only a human dismiss releases them.
  Field-vanish stales both tiers.
- **No new job substrate; egress-pinned triggers.** Both passes are pure O(fields) in-DB logic —
  exactly what §1 lets the API run inline. Triggers: post-discovery (best-effort, own txn, beside
  the suggestion hook), in-pass at profiling, and admin `POST /api/sources/{id}/pii-scan` — which
  runs the schema-tier detector + retro-scrub over already-persisted rows ONLY, no network fetch;
  profile-tier detection happens exclusively inside `profile_source`, where the sample is already
  in memory (negative test: no fetch hook invoked).
- **Hardened mutation surface — the audited paths are the ONLY paths.** Lane-generated generic
  CRUD would otherwise open unaudited side doors: `status` is rejected in the generic
  `PUT /api/pii-flags/{id}` payload (422; transitions only via the audited confirm/dismiss
  endpoints), `DELETE` writes an audit event or returns 405, and `field_profiles` service updates
  route through the same suppression check the profiling pass uses (active flag ⇒ value columns
  forced NULL) — so a plain admin PUT cannot re-write raw values into a suppressed row. `[FF]`,
  sequenced immediately after confirm/dismiss.
  **Built differently:** only the audit half shipped. `PUT` and `DELETE /api/pii-flags/{id}` write
  `audit_logs`, but `PUT` still accepts `status`, and `PUT /api/field-profiles/{id}` writes value
  columns with no suppression check.

**Data model (1 new table):**

```
pii_flags (category CHECK-enum: direct_identifier|contact|government_id|financial|health|
           date_of_birth|location|credential|network_identifier|other;
           detection_tier: schema|profile; status: flagged|confirmed|dismissed|stale;
           confidence, rationale, fingerprint)                                        [E]
  ├─ discovered_field_id → discovered_fields(id) ON DELETE SET NULL, indexed          [F+]
  └─ dataset_id → datasets(id) ON DELETE SET NULL, indexed (reconcile scope)          [F+]
```

Standing contract applies, with two lane caveats: `confidence` as FLOAT is unverified against the
`[E]` grammar (only CHECK-enums are proven) — verify before filing, else interim-type it as a
string or add via `[F+]` once supported; and the §3 soft-delete clause is known doc-vs-code drift
(no shipped table has `deleted_at`).

**Feeds & at-rest exposure (widened):** masking (RBAC pillar) keys policies on `category` +
`status='confirmed'`; RTBF scopes erasure to datasets holding confirmed flags. A flag on an
`is_key` field is emitted at elevated confidence, and its rationale enumerates ALL THREE verbatim
value stores — `ingested_records.business_key`, `ingested_records.name` (the `rec:<key>` copy),
and `delta_cursors.cursor_value` (non-numeric/non-timestamp cursor kinds pass any value through
unchanged) — so the hash-at-rest operator question covers every surface, not just the key column.

**Built differently:** nothing masks on these flags yet (see #77), and an erasure runs on the
request's own `dataset_id` with no flag check. The key-field rationale names only the op-log, not
all three stores. `ingested_payloads` is now a further verbatim store, and the OData feed serves its
values with no PII check.

### RBAC & data masking (#77)

**Not built:** only `admin` and `user` exist (`backend/app/auth/authorization.py`, about 120
`require_role` route dependencies). `steward`, `pii_reader`, `pii_status`, `app/masking/engine.py`,
`is_masked` and the steward transition endpoint do not exist. Classification lives in `pii_flags`
and decisions are admin-only. What runs is #75's write-time NULLing and chart withholding, so
values of unflagged fields stay readable by any authenticated user.

**Role catalog — four flat JWT roles, no hierarchy, no role tables.** `admin` (mutations) and
`user` (authenticated read) stay exactly as enforced today (`require_role` per endpoint, 110 call
sites untouched). Two additive roles: **`steward`** — may mutate *governance metadata only* (PII
classification), gated `require_any_role(["admin","steward"])`; and **`pii_reader`** — a pure
capability role: holders receive unmasked values, everyone else masked responses. An
analyst/viewer split is rejected: with no per-user resources and no tenant axis both collapse
into `user` — catalog theater. Roles remain IdP-issued JWT claims via `AUTH_ROLE_CLAIMS`; the DB
gets no users/roles tables — a second role authority is a standing inconsistency. `admin` does
NOT imply `pii_reader` (infra privilege ≠ data privilege); a small shop grants both to one human
in the IdP.

**Classification — four-state, two-tier, mirroring the suggestion engine.** `discovered_fields`
gains `pii_status ∈ (none, suspected, confirmed, cleared)`. Two normative lane caveats: (a) the
CHECK-enum grammar (CodeAgent#392) is proven on the `[E]` entity lane only — no `[F+]` has ever
emitted an ALTER-TABLE CHECK constraint — so this column is a **probe** `[F+]`; if it
fail-closes, file the engine item (`[F+]` ALTER-TABLE CHECK-enum grammar) and unblock with a
hand-authored migration (0023 style, 0034 CHECK precedent). (b) The column is nullable with no
default and discovery never sets it, so **NULL ≡ `none`** at every read/transition site
(`COALESCE(pii_status,'none')`), with a NULL-row fixture test asserting it classifies, masks, and
transitions exactly like `'none'` — otherwise lane tests pass against the literal while every
production row is NULL. Tier 1: a pure name-token classifier marks `none → suspected` during
discovery reconciliation (it ships its OWN checked-in field-name corpus fixture with exact
expected suspect counts — no phantom fixture paths). Tier 2: a steward transition endpoint
confirms or clears; `confirmed`/`cleared` are sticky against re-discovery (human decisions are
never overwritten by a rules pass), and `cleared` keeps a steward-rejected false positive
distinguishable from never-classified `none`. **The transition endpoint is the ONLY writer:**
`pii_status` is stripped from `DiscoveredFieldCreate/Update` (PUT carrying it is ignored/422), so
generic admin CRUD cannot flip `confirmed → cleared` with no audit and no scrub.

**Enforcement seams — endpoint deps + one explicit masking pass; no RLS.** Row-level security is
rejected: single-org on-prem, no tenant axis, and RLS taxes every repository plus the worker's
direct SQL for zero current need. Masking lives at the *serialization seam*: a pure engine
`app/masking/engine.py` — `mask(rows, pii_map, roles) → rows'` — deterministic, fixture-tested,
applied explicitly in **every** handler returning a value-bearing response — create/update echoes
included, not just list/get (a `PUT {}` echoes the full raw row to an admin who by design lacks
`pii_reader`). Response middleware is rejected (schema-blind, opaque, streaming-hostile);
explicit application is greppable, and the surface is enumerable:
1. `field_profiles.min_value/max_value/most_common_value` — today's live leak: raw sampled ERP
   values readable by any authenticated `user`;
2. `ingested_records.business_key` **and its `name` twin** — `name` is written as `rec:<key>`,
   the business key verbatim, so both are nulled/redacted together when ANY key field of the
   dataset is PII-flagged (composite string ⇒ dataset-granularity check); the standing rule is
   amended to *"schema names, excluding synthetic name columns derived from record values"*;
3. the Milestone-6 landing-table query path MUST route through the same engine (an M6 dependency
   — designed now, built then).
Field names, dataset names, suggestion titles are schema, never masked — suggestions bind field
*names* only (verified: the suggestion spine is values-free), and masking metadata would blind
the whole UI for no privacy gain (accepted residual: sensitive column names). Cost note,
corrected: the value-bearing list endpoints are currently UNPAGINATED full-table reads —
full-table masking is accepted for `field_profiles` (small); `ingested_records` needs a
pagination item before its masking FF lands.

**Masked representation: `null` + `is_masked: true`** (additive response field), never a fake
token — fake values would flow into charts as data. `suspected` masks exactly like `confirmed`
(fail closed; a steward clears false positives). Composition is fail-closed end to end:
anonymous/dev-mode users carry `roles=[]` ⇒ masked even with `AUTH_ENABLED=false`; unmasking
always requires an affirmative `pii_reader` claim.

**Minimize, then mask.** Read-time masking alone leaves raw values at rest, so writes are gated
too: profiling stores NULL min/max/most_common for PII-flagged fields (counts still computed —
aggregates, not values), and the `confirmed` transition NULLs the field's existing profile values
in the same transaction. Read-time masking covers the residual window (values sampled before
flagging) and per-role differences.

**Audit — transactional via a cursor-sharing seam.** `pii_status` transitions write `audit_log`
in the SAME transaction as the status UPDATE + profile scrub. `AuditService.write` as-is cannot
deliver that (its repository opens its own connection and commits independently): the repository
gains a cursor-accepting `write_event(cur, event)` variant so the steward endpoint passes its
open cursor; the test kills the audit INSERT and asserts the transition did NOT persist. Unmask
reads emit a structured log line (actor, field ids) for now; audit-table read events are
deferred until compliance demands them.

Lanes: 1×`[F+]` (the enum-column probe), ~7×`[FF]` (each ≤8 files, pure-module-first), 1×`[MI]`
(IdP roles), 0×`[E]` — no new tables. Engine-feature candidates: `[F+]` ALTER-TABLE CHECK-enum
grammar; role-parameterized mutation gates in `[E]` ACs; a status-transition sub-resource lane
shape; non-FK scalar `[F+]` types (boolean).

### Right-to-be-forgotten (#76)

**Decision: delete-on-request + hashed suppression list; business keys stay verbatim at ingest.**
Pseudonymizing `business_key` at ingest was rejected: it protects only the op-log while the M6
landing tables will hold full payloads verbatim anyway (illusory protection), and it destroys the
op-log's operational value — readable lineage, debuggability, the idempotency key. Erasure is a
physical `DELETE` — stated precisely, since soft-delete is doc-aspirational, not on `main` (no
shipped table has `deleted_at`; repositories physically DELETE): **erasure targets are physically
deleted; governance records are retention-protected** — the lifecycle `[FF]` blocks `DELETE` on
completed/rejected `deletion_requests` (409), so lane CRUD cannot destroy a proof-of-erasure
record.

**Not built:** that guard does not exist. `DELETE /api/deletion-requests/{id}` removes a row in any
status, and the admin-only generic `PUT` can set `status` directly.

**`deletion_requests` is a third claim spine, not a generalized `runs`.** §1 settled the
substrate; a generic jobs table would be a §2 build-then-migrate violation and could not be
minted by the `[E]` lane. First live use of the enum AC grammar: `status` constrained to one of
(received, verifying, executing, completed, rejected). Lifecycle (mutations AND reads admin-only
— `subject_key` is PII): `received` (POST create: `dataset_id` + `subject_key`, normalized with
the same 255-cap) → admin `POST …/verify` after off-system identity verification → `verifying`
(= verified-and-queued, THE claimable state) → worker claim flips `verifying→executing` (atomic
SKIP LOCKED) → `completed`; `POST …/reject` valid from received/verifying only; every transition
status-guarded, terminal states win. **No `failed` state by design:** erasure is pure in-DB and
idempotent, so failure resets `executing→verifying` with `attempts+1` + `error_detail`; the claim
filters `attempts < 5`; the reaper resets stale `executing` rows the same way. Verification-forced
guards: (a) finalize and failure-reset are fenced with **`attempts` as a generation token** (the
claim `RETURNING attempts`; `WHERE status='executing' AND attempts=<claimed>`) — the reaper
resets rather than terminally fails, so a woken zombie could otherwise finalize onto a retry's
in-flight claim; (b) an attempts-exhausted request must stay visible while a statutory deadline
(GDPR: one month) runs — admins triage on `attempts` + `error_detail`, the list endpoint gains a
`needs_attention` filter (`status='verifying' AND attempts>=5`), and a test asserts exhausted
rows are never re-claimed; (c) the admin-only **read-tightening is its own tiny `[FF]` ordered
immediately after the `[E]` merge** — lane-standard reads are `require_authenticated_user`, which
would expose raw `subject_key` to role `user` for the whole build window; no requests may be
created before it lands; (d) the 12-field `[E]` mint exceeds proven lane width (~7 on
`discovery_runs`) — attempted first (it exercises the enum grammar at realistic width, engine
evidence either way) with the fallback pre-written: `[E]` mint of 4 + an `[F+]` chain for the
remaining 8 scalars. Inline mode (`INGEST_EXECUTOR=inline`) executes synchronously inside
`/verify` — erasure needs NO egress, so it never gates on `ENABLE_INAPI_EGRESS`; identical rows
either way (§1).

**Not built:** the `needs_attention` filter in (b). The list endpoint takes no filters, so admins
read `attempts` and `error_detail` from the full list. The attempts cap itself ships and is tested.

**One erasure transaction** (all-or-nothing): (1) `DELETE FROM ingested_records WHERE
dataset_id=? AND business_key=?` — the `name` column's `rec:<key>` copy dies with the row;
(2) NULL `field_profiles.min/max/most_common_value` for ALL the dataset's fields — the subject's
PII can sit in any profiled column, so surgical matching under-deletes; counts stay (non-personal
aggregates); (3) INSERT `suppression_entries` ON CONFLICT DO NOTHING; (4) the audit
proof-of-erasure (`erasure_executed`, details = counts + `subject_key_hash`, never the raw key) —
written **on the same open cursor** via the shared transaction-sharing audit seam, because
`AuditService.write` commits on its own connection and would make erasure-without-proof (and
proof-without-erasure) reachable; a test forces the audit INSERT to fail and asserts the op-log
delete + suppression entry rolled back. The proof's actor is the `verified_by` admin sub captured
at `/verify` (the erasure executes on that admin's authority; details note
`executed_via=worker|inline`; `system:worker` only as fallback); (5) finalize: counts,
`completed_at`, `subject_key` NULLed **and `name` overwritten** (`dr:<first-8-of-hash>` — the
free-text `name` is where an admin would naturally paste the identifier). The completed row +
audit event ARE the proof of erasure without retaining the identifier.

**Built differently:** step 1 also deletes the subject's `ingested_payloads` row, and
`records_deleted` counts both. Step 4 is `record_audit` on the same cursor: an `audit_logs` row with
`action='delete'`, `entity_type='erasure'` and the counts + `key_hash` in `detail`, with no
`executed_via` and a fallback actor of `system`. Step 5 NULLs `subject_key` but does not overwrite
`name`, so an identifier pasted there survives the erasure.

**Suppression (re-ingest must not resurrect):** `key_hash = hex(HMAC-SHA256(pepper,
dataset_id‖0x00‖business_key))` — deterministic (matchable at ingest), non-attributable without
the pepper (plain SHA-256 rejected: business keys are low-entropy, dictionary-reversible).
Folding `dataset_id` into the HMAC input makes `key_hash` alone globally unique → single-column
unique index; CodeAgent#393 stays off the critical path. The pepper lives ONLY in the secret seam
(`aidw/governance/suppression_pepper`, env-resolved interim; Vault later is resolver-internal) —
never a DB column — and is write-once: rotation orphans every entry, so pepper custody is
DB-backup-grade `[MI]`. **Built differently:** the pepper is read from the environment variable
`AIDW_SUPPRESSION_PEPPER` (`backend/app/governance/hashing.py`), not through a namespaced secret
seam. Three verification-forced semantics:

- **Lazy, fail-closed filter.** `apply_rows` loads the dataset's suppression entries first; when
  empty it skips hashing entirely — no pepper resolution, so RTBF never becomes a hard runtime
  dependency of plain ingestion on pepper-less deployments. With entries present, a missing
  pepper FAILS the run — never silent resurrection.
- **Watermark still advances.** Suppressed rows skip ONLY the op-log upsert; their cursor values
  still enter the watermark candidate list (suppression is not a data error — the row was validly
  fetched). Otherwise a fully suppressed page recreates the poisoned-watermark wedge and
  refetches forever. Test: full page suppressed ⇒ `rows_suppressed` = page size, zero op-log
  rows, watermark ADVANCED. `runs.rows_suppressed` is the observable output state (the
  reward-hack guard).
- **Profiling consults the same suppression module.** `profile_source` (auto-triggered after every
  successful ingest) re-samples the LIVE source — unfiltered, it would repopulate raw
  min/max/most_common with the subject's values one cycle later, resurrecting exactly what was
  erased, under the same premise the suppression list exists for (the source may not have erased the
  subject). It derives each sampled row's business_key via the dataset's `is_key` fields (same
  field-position order as ingest, so the hash matches what the erasure recorded) and drops suppressed
  rows before `_stats`; like ingest it hashes only when the dataset has suppression entries and fails
  closed — rolling back the profiling transaction rather than resurrecting — if the pepper is then
  missing. Test: erase, re-profile from an unchanged fixture, assert the subject's values are absent.

**M6 landing arrival contract (designed now, lands compliant):** every per-dataset landing table
MUST carry an indexed `business_key` (same derivation); the landing writer consults the same hash
module before insert; the erasure executor gains a registry-driven `DELETE FROM landing_<ds>`
step; backfills check suppression before writing. Ships `[MI]` with the landing DDL.
**Built differently:** the shared `ingested_payloads` table meets this without a registry: it has
`business_key`, `apply_rows` lands only non-suppressed rows, and the executor deletes from it in the
erasure transaction.

**Lane gaps → engine candidates:** the `[E]` lane cannot express admin-only READS (interim `[FF]`
tightens the router); verify/reject is the second live status-transition endpoint shape (after
suggestion accept/dismiss) — a transition-lane AC grammar is warranted.

### Retention (#80)

Retention is **policy-driven, sweep-executed, audit-evidenced**: one config entity
(`retention_policies`), one work spine (`retention_runs`) on the settled SKIP-LOCKED claim
substrate, zero new runtimes. Retention is a **ceiling** — RTBF's `deletion_requests` delete
sooner regardless of schedule; nothing here ever extends a row's life.

**Built differently:** what runs is a manual purge of one policy at a time, from the Data retention
screen or `POST /api/retention-policies/{id}/sweep` (`backend/app/retention/service.py`). The notes
below give the details.

**Data model — decomposed to lane-proven width.** The `[E]` lane mints name + string/enum fields
only (the 0017 precedent; ints/bools/timestamps have always arrived as `[F+]`), so:
`retention_policies` `[E]` = name + `table_class` enum (`ingested_records | field_profiles |
runs | discovery_runs | connection_tests | audit_log | landing`) + `action` enum
(`purge | anonymize`) + **`scope` enum (`class | dataset`)**; then `[F+]`
`retention_period_days` (INTEGER), `[F+]` `is_enabled` (BOOLEAN), `[F+]` `dataset_id` (nullable
FK → `datasets`, SET NULL, indexed). `retention_runs` `[E]` = name + `status`/`trigger` enums;
then `[F+]` each for `started_at`, `finished_at`, `policies_applied`, `rows_purged`,
`error_summary` — a third run spine, kept separate per the §2 precedent. Because the `[F+]`
"timestamp" precedent emitted `VARCHAR(32)`, the due-check and reaper key on the contract
`created_at`/`updated_at` (real TIMESTAMPTZ); real timestamp typing is filed as an engine gap.

**Built differently:** `table_class` allows `connection_tests`, `runs`, `discovery_runs`,
`ingested_records` and `field_profiles` only. `dataset_id` is `ON DELETE CASCADE` (migration 0045).
A `retention_runs` row covers one policy: `policy_id`, `records_purged`, `records_anonymized` and
`error_detail`, with no `started_at`, `finished_at` or `policies_applied`.

1. **Granularity + the scope fail-close.** Class + optional dataset, most-specific wins;
   `dataset_id` honored only for dataset-partitioned classes (`ingested_records`,
   `field_profiles`, `landing`), ignored elsewhere. The `scope` enum exists because
   `ON DELETE SET NULL` would otherwise silently promote a deleted dataset's (possibly very
   short) policy into a class-wide purge of EVERY dataset's rows: the resolver fail-closes any
   `scope='dataset' AND dataset_id IS NULL` policy into `error_summary` — never widened, never
   applied — and the sweeper may additionally flip it `is_enabled=false` + audit.
   `field_profiles` has no `dataset_id`: dataset scoping resolves via JOIN through
   `discovered_fields`, and orphaned profiles (`discovered_field_id IS NULL` — precisely the
   stale-PII rows) always fall under the class-wide policy. Same-scope duplicates: shortest
   period wins (most restrictive, deterministic).
   **Built differently:** partial unique indexes (migrations 0048, 0049) allow one policy per class
   and one per class + dataset, and each sweep runs only the policy it names, so there is no
   most-specific or shortest-period resolver. A dataset-scoped policy works for `ingested_records`
   only; on `field_profiles` it fails closed.
2. **Defaults: telemetry seeded, business data operator-set.** A seed migration `[FF]` inserts
   enabled 365-day purge policies for `connection_tests`/`runs`/`discovery_runs` — pure telemetry
   whose unbounded growth is the on-prem failure mode; their inbound FKs are ON DELETE SET NULL,
   so purging the spine degrades lineage, never integrity. `ingested_records`, `field_profiles`,
   `audit_log`, `landing` ship with NO policy: a warehouse must never destroy business data by
   default. Defaults are visible, editable rows, never sweeper constants.
   **Not built:** no seed migration exists. No policy exists until an admin creates one.
3. **Actions, with normative scrub + cutoff matrices** (a freeform build must not guess).
   `purge` = batched hard DELETE — the only *bulk/automated* deletion path (generic CRUD
   hard-deletes too; no `deleted_at` exists on `main`) — 10k-row batches, commit per batch,
   resumable (the cutoff predicate is stable). `anonymize` = per-class column scrub, row survives
   as a countable skeleton, **idempotent**: the WHERE clause excludes already-scrubbed rows
   (`AND business_key IS NOT NULL`, …) and only newly scrubbed rows enter run counters and audit
   details. Scrub matrix: `ingested_records` → `business_key → NULL` (NULLs are distinct under
   the unique index) **and `name → 'rec:anonymized'`** (NOT NULL column — scrubbing the key while
   `name` keeps `rec:<email>` verbatim would be a false compliance claim); `field_profiles` →
   min/max/most_common_value → NULL. **`audit_log` is purge-only** — `actor_sub` is NOT NULL, so
   a NULL-scrub would fail every batch; unsupported class/action combos fail-close into
   `error_summary`. Hash-pseudonyms rejected: a re-hashable key is pseudonymization, not
   anonymization. Cutoff matrix: `ingested_records`/`field_profiles` → `updated_at` (last-seen
   semantics — `created_at` would purge live, daily-re-seen records);
   `runs`/`discovery_runs`/`connection_tests` → `created_at`, terminal statuses only; `audit_log`
   → `timestamp`; landing → `ingested_at` partitions. The seed `[FF]` also indexes
   `ingested_records(updated_at)` — the warehouse's largest table must not seq-scan per batch.
   **Built differently:** `purge` is one unbatched `DELETE`, and `anonymize` fails closed ("purge
   only"). The cutoff is `created_at` for every class, including `ingested_records`, which is the
   case this item warns about. The `updated_at` index was not added.
4. **Scheduling: the worker self-enqueues.** Each poll, the worker inserts a `scheduled`
   retention_run when none ran within `RETENTION_SWEEP_INTERVAL_HOURS` (default 24), guarded by a
   partial unique index (at most one non-terminal run — no overlap, no duplicate-enqueue race);
   the existing reaper pattern covers stale `running` rows. `POST /api/retention/sweep` `[FF]`
   (admin) enqueues a `manual` run; in inline mode it executes synchronously — a sweep is pure
   in-DB, no egress, safe without `ENABLE_INAPI_EGRESS`; same executor on both paths, identical
   rows (§1 rule). An inline sweep of a large backlog can outlive HTTP timeouts (documented —
   mirrors inline ingest; optionally capped via `RETENTION_INLINE_MAX_BATCHES`, remainder picked
   up by the next sweep — safe because the cutoff predicate is stable).
   **Not built:** the worker neither enqueues nor runs sweeps, and neither setting exists. A sweep is
   per policy and synchronous, at `POST /api/retention-policies/{id}/sweep`. `reap_stale_sweeps`
   (`backend/app/retention/reaper.py`) exists, but only tests call it.
5. **Audit evidence — self-consistent.** Every applied policy writes one audit row:
   `action='retention_purge'`/`'retention_anonymize'`, `actor_sub='system:retention'`, entity =
   the policy, details = class, dataset, cutoff, row count — counts and cutoffs ONLY, never
   purged values. The audit INSERT goes on the same open batch cursor via the shared
   `write_event(cur, event)` seam (`AuditService.write` commits independently — the "commits in
   the final batch's transaction" guarantee is unimplementable through it). Erasure-evidence
   actions are hard-exempt from audit purge in the sweeper's WHERE clause:
   `action IN ('retention_purge','retention_anonymize','rtbf_erasure')` — anonymization evidence
   IS erasure evidence, and demonstrating erasure is itself a retention obligation. A mid-sweep
   crash still leaves partial counts on the reaped `retention_runs` row; re-sweeping is
   idempotent. And the blast-radius control is itself audited: a small `[FF]` instruments
   `retention_policies` create/update/delete with audit writes carrying the real AuthUser actor —
   the first CRUD audit writer — so shorten-sweep-restore leaves a trace.
   **Built differently:** policy create/update/delete are audited as designed, but a sweep writes no
   audit row. The `retention_runs` row commits with the `DELETE` and is the only evidence.
6. **Landing purge contract (binds the M6 `[MI]`).** Every typed landing table MUST carry a
   last-seen `ingested_at TIMESTAMPTZ NOT NULL` and be range-partitioned on it (monthly); PG15
   cross-partition UPDATE re-homes re-seen rows, so old partitions hold only rows "not seen
   since". Landing retention = `ALTER TABLE … DETACH PARTITION CONCURRENTLY` + `DROP` — no dead
   tuples, no vacuum debt, files returned to the OS. A landing table not matching the contract is
   skipped fail-closed and reported. `ingested_records` itself CANNOT take this path (partitioned
   unique indexes must embed the partition key, and `UNIQUE(dataset_id, business_key)` is global
   across time) — it stays DELETE-based.
   **Not built:** there are no partitioned landing tables, and `ingested_payloads` is not a
   retention class, so purging `ingested_records` leaves the matching payload rows in place.
7. **"Securely purged", defined honestly.** A purge makes rows immediately irrecoverable through
   every AIDW surface (API and SQL); physical remanence persists in dead tuples until autovacuum
   reuses pages, in WAL until it recycles, and in backups until they rotate. The sweeper never
   runs VACUUM FULL (ACCESS EXCLUSIVE lock, 2× disk). Bounding remanence is operator infra
   `[MI]`: LUKS at-rest encryption (the encryption pillar's crypto-erase story) + a backup/WAL
   retention runbook stating the true end-to-end erasure horizon. Audit wording says "purged"
   meaning exactly this — never more.

### Encryption at rest & in transit (#78)

**Threat-honest scoping (the one framing decision).** AIDW is single-host compose;
container↔container bytes on the docker bridge never leave the kernel. The wire that matters is
the LAN: compose publishes 5432 (Postgres, password auth, plaintext), 9000 (API, bearer tokens
plaintext), 8080 (UI) — and `test-db`'s hardcoded `"5433:5432"`, carrying the SAME `DB_PASSWORD`
as production. Effort is ordered edge-inward: (1) close/loopback-bind published ports —
5432/9000/8080 are already env-parameterized, so their loopback binds are pure `.env` values
(`DB_PORT_HOST=127.0.0.1:5432`, …), while the `test-db` port needs the one real compose diff
(loopback-bind, remove, or parameterize) — "LAN entry becomes the nginx edge only" is false until
5433 closes; (2) TLS at the one remaining LAN edge (the frontend nginx, which already proxies
`/api`); (3) TLS on the Postgres link for the day the worker or admin psql is remote;
(4) source-egress TLS policy. Intra-compose mTLS is explicitly NOT pursued.

**Current state:** the backend port now binds to `127.0.0.1` by default (`BACKEND_BIND_HOST` in
`docker-compose.yml`). 5432, 8080 and the hardcoded 5433 are still published on all interfaces, and
`test-db` still shares `DB_PASSWORD`.

**At rest — block layer, not database layer.**
- **LUKS on the host path backing the Postgres volume is THE at-rest mechanism `[MI]`.** Vanilla
  Postgres 15 has no TDE (fork-only: EDB/Percona/pg_tde); adopting a fork contradicts the
  `postgres:15-alpine` baseline. LUKS covers disk theft/RMA/disposal with zero app change, and
  covers `ingested_records.business_key` + `field_profiles` raw sample values **at rest only** —
  their live-API exposure belongs to the masking pillar, not this one.
- **pgcrypto column encryption: rejected.** The §1 secret boundary means no secret ever lands in
  a DB column, so there is nothing for pgcrypto to protect that Vault doesn't protect better —
  and its key would live in `.env` beside `DB_PASSWORD`: encrypting the disk with a key kept on
  the same disk.
- **Backups inherit the rule `[MI]`:** dumps land on the encrypted mount; off-host copies are
  age-encrypted. One unencrypted `pg_dump` silently un-does LUKS.

**In transit — three planes.**
1. **Client→edge:** TLS terminates at the existing frontend nginx (one hop, one cert); backend
   9000 stops being LAN-published. Compose-native pattern: nginx listens on **8443 (ssl) inside
   the container and compose publishes `443:8443`** — the frontend runs `read_only` +
   `cap_drop: ALL` on an unprivileged port by design; binding 443 in-container would lean on a
   Docker sysctl default instead of the repo's established idiom. Cert from the internal CA; the
   conf diff bundles into the same `[MI]` — compose/nginx-only diffs have no assertable test
   surface, flagged as a CodeAgent engine candidate (infra lane, healthcheck-proven — now resting
   on the TLS server block, since the port binds turned out to be `.env`-only).
   **Not built in this repo:** `app/nginx.conf` listens on 8080 only and compose publishes no 443. A
   compose comment mentions a TLS proxy, but nothing here configures one.
2. **App→Postgres:** `get_connection_params()` gains env passthrough
   `DB_SSLMODE`/`DB_SSLROOTCERT` `[FF]` — absent = today's exact params dict, so nothing breaks.
   The operator then provisions the server cert (`ssl=on`), loopback-binds the published 5432,
   and flips `verify-full` `[MI]`. Ships even though same-host today: it is the precondition for
   a remote worker (post-M6) and remote psql.
   **Not built:** `get_connection_params()` has no SSL settings.
3. **Egress (the in-repo core):** `verify_tls` is stored (0009) but read by NOTHING — all three
   fetch seams (discovery / profiling / ingest `_fetch_*`) verify by urllib default, so
   `verify_tls=false` silently lies to the user. One shared opener (`app/egress/http.py`)
   replaces the three copies — §1's "one secret seam" gets a matching **one egress seam** —
   split into TWO `[FF]`s to respect freeform caps: **FF-a** the seam module + verify policy +
   the three call-site replacements, where the opener also honors the stored-but-ignored
   `timeout_seconds` (fallback 30) — otherwise the seam re-creates the very "accepted but not
   implemented" defect class it exists to kill; **FF-b** policy-error surfacing + the
   http-with-credentials refusal (callers pass a `has_credentials` bool; the seam stays DB-free).
   Policy: verify by default; `verify_tls=false` honored ONLY under `ALLOW_INSECURE_EGRESS=true`
   (default false, mirroring `ENABLE_INAPI_EGRESS`); plain-`http` stays allowed for
   credential-less demo sources but is REFUSED once the source has `source_credentials`.
   **Refusals must be observable at every caller:** ingest already lands them in
   `runs.error_detail`; profiling must catch `EgressPolicyError` SEPARATELY from generic fetch
   failures and re-raise to a 422 with the sanitized message — its per-dataset `continue` would
   otherwise 200-succeed with zero datasets profiled, the exact silent lie this pillar kills;
   discovery must map it to a 422 (its endpoint catches only `LookupError`/`DiscoveryError`, and
   no `discovery_runs` row exists on that path to carry a message). One refusal assertion per
   caller. Scope note, stated out loud: the fourth `urlopen` — the auth-plane `_fetch_jwks` — is
   deliberately OUTSIDE the source-egress seam (operator-configured target, verifies by default;
   the auth pillar owns it if it ever needs CA/proxy policy). Private-CA endpoints (SAP
   landscapes): `source_connections.ca_bundle_ref` `[F+]` — a resolver-namespace ref
   (`aidw/sources/<id>/ca_bundle`), never PEM-in-DB — **but the interim env/file resolver did
   not exist when this was verified** (§5 M0 #3 planned it), so an explicit predecessor `[FF]`
   ships `app/secrets/resolver.py` first and the CA-resolution `[FF]` depends on it.
   **Built differently:** every source fetch goes through `fetch_bytes` in
   `backend/app/egress/http.py`, which adds credential resolution, redirect rules and a destination
   policy (`backend/app/egress/policy.py`: `EGRESS_POLICY`, `EGRESS_ALLOWED_HOSTS`). The env-only
   resolver now exists as `backend/app/egress/secrets.py`. Connection tests, discovery and ingest
   honor `timeout_seconds`; profiling and chart fetches use a fixed 30 seconds. A refusal raises
   `EgressDestinationDenied`: discovery returns 422, ingest fails the run and a connection test
   records `unreachable`, but profiling still logs and continues, so a fully refused source returns
   200 with zero datasets profiled. Not built: any read of `verify_tls`, `ALLOW_INSECURE_EGRESS`,
   the http-with-credentials refusal (Basic credentials go over plain `http`), `ca_bundle_ref` and
   `app/secrets/resolver.py`. `_fetch_jwks` now uses `requests`, and the optional Flowable proxy
   also fetches outside this seam.

**Secrets posture (reaffirmed, extended).** `secret_ref`-only stands. This pillar adds:
**endpoint URLs must not carry userinfo** — `https://user:pass@…` would store a verbatim secret
in `source_connections.endpoint` and echo it from every GET, log line, and future audit row; 422
on create/update `[FF]`. `.env` (holds `DB_PASSWORD`, `AUTH_DEV_TOKEN`) → `0600`, owner `aidw`,
on the LUKS mount `[MI]`. The M6 Vault `[MI]` widens scope: KV for credentials + `ca_bundle`
blobs; Vault PKI as the internal CA issuing the nginx/Postgres certs. Insecure-egress events are
LOG-warned, not audit-written — first-writer wiring belongs to the audit pillar, not smuggled in
through an egress module.

**Not built:** `source_connections.endpoint` has no userinfo check, so such a URL is stored and
echoed as written. Vault and insecure-egress logging do not exist.

### Cross-pillar contracts

- **One audit actor convention + one transactional seam.** System-originated events share
  `actor_sub='system:<component>'` (`system:pii-watchdog`, `system:retention`, `system:worker`);
  RTBF proof rows carry the `verified_by` admin's sub instead (the erasure executes on that
  admin's authority). Three pillars independently hit the same wall — `AuditService.write`
  commits on its own connection — so the cursor-accepting `write_event(cur, event)` repository
  variant is ONE shared prerequisite for every same-transaction audit guarantee (steward
  transitions, erasure proof, sweep evidence). **Built differently:** the seam is
  `record_audit(cur, …)` on `audit_logs`, not a `write_event` variant. PII decisions use their own
  INSERT into `audit_log`, and sweeps write no audit row.
- **Masking keys on confirmed flags.** The watchdog's `pii_flags` (`category` +
  `status='confirmed'`) are the policy input for RBAC masking; RTBF scopes erasure to datasets
  holding confirmed flags. One classification substrate, three consumers. **Not built:** neither
  consumer reads the flags; profiling and charts do, on any active flag.
- **RTBF overrides retention — floor vs ceiling.** Retention schedules are a ceiling (nothing
  outlives its policy); `deletion_requests` are a floor (delete sooner regardless of schedule);
  neither ever extends a row's life.
- **The M6 landing-table DDL contract binds three pillars at once:** an indexed `business_key`
  (same derivation) + suppression check before insert (RTBF); `ingested_at TIMESTAMPTZ NOT NULL`
  + monthly range partitioning (retention's DETACH/DROP purge); the landing query path routes
  through the masking engine and the volume lives on the LUKS mount (masking + encryption).
  Ships `[MI]` with the landing DDL; a non-conforming table is skipped fail-closed.
  **Built differently:** `ingested_payloads` meets the RTBF part only. It is not partitioned and its
  read paths use no masking engine.
- **Engine gaps surfaced (prime directive: lane gaps become engine features):** positive-integer
  CHECK grammar (`<field> constrained to be a positive integer` — `retention_period_days` interim
  relies on sweeper-side fail-close), real timestamp column typing (the `[F+]` "timestamp"
  precedent emitted `VARCHAR(32)`), and a standalone-index-on-existing-column lane (today
  column+index ship only together) — all extending the CodeAgent#392/#393 line, alongside the
  per-pillar candidates above (`[F+]` ALTER-TABLE CHECK-enum, partial/predicate unique index,
  admin-only reads, status-transition endpoints, non-contract-table support).
  **Current state:** later migrations carry a positive-integer CHECK (0046), a partial unique index
  (0048), a standalone index (0056) and a real timestamp column (0105). The engine is not in this
  repo, so whether those lanes now exist was not checked.

---

*Generated from a multi-agent design workflow + adversarial verification, 2026-07-05. Refile the
backlog items above as CodeAgent issues per milestone; the schema-discovery FK lineage
(`discovered_fields.dataset_id`) folds into Milestone 3.*
