# AIDW Behavioral-Layer Architecture

Status: **design, verified** · Owner: CodeAgent (AIDW instance) · Supersedes: ad-hoc entity work

This is the target architecture for AIDW's behavioral layer — the vision's substance beyond the
CRUD scaffold that is already on `main` (`sources → datasets → discovered_fields`). It was
produced by a multi-agent design workflow (3 independent proposals → judge-panel synthesis) and
then **adversarially verified** across four lenses. Constraint-fidelity held; the buildability,
vision-completeness, and risk lenses surfaced defects in the *backlog* that are corrected here
(see [§7 Verification corrections](#7-verification-corrections-applied)).

The four capabilities, in vision priority: **connectivity (OData-first) → schema discovery →
CDC ingestion → dynamic dashboard suggestion.**

---

## 1. Runtime topology

Two runtimes, one Postgres, one secret seam:

- **API process** (existing FastAPI + Alembic + Postgres) — owns *all* metadata/state CRUD, all
  reads, and *thin behavioral seams* that either **enqueue** work (insert a `queued`/`pending`
  row) or run **pure in-DB logic** over already-persisted rows (accept a suggestion; run the
  suggestion rule engine over stored profiles). **Zero source egress; never touches raw secrets.**
- **Connector/ingestion worker** — ONE shared service (operator-provisioned; see §5). Owns *all*
  egress and heavy I/O: OData `$metadata` GET, DB `information_schema`, CDC drain/poll/diff, row
  landing, profiling scans. Claims work via `SELECT … FOR UPDATE SKIP LOCKED`, resolves
  `secret_ref` at connect time, writes results + status in one transaction.
- **One job substrate (decided once):** every behavioral trigger is a DB work-table row in a
  `queued`/`pending` state the worker drains via skip-locked polling — `connection_tests`,
  `discovery_runs`, and `runs` alike. A real broker (Redis/LISTEN-NOTIFY) is a later
  scale-triggered issue.
- **Secret boundary (one rule):** credentials live ONLY as `secret_ref` (opaque path) +
  non-secret `principal`. The namespace is **`aidw/sources/<id>/<key>` from day one.** An interim
  env/file resolver (secrets are `.env` on the host today) satisfies it now; **Vault later is a
  resolver-internal swap, not a schema or API change.** No secret material ever lands in a DB
  column, `audit.details`, an `error`/`message` field, or a log line.
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
2. **Two run spines, kept separate.** `discovery_runs` (discovery) and `runs` (ingestion) have
   different shapes/lifecycles. `field_profiles`/`suggestions` get a `run_id` FK only in breadth,
   once `runs` is on `main` — the *only* cross-capability FK edge in the whole plan.

---

## 3. Data model — 18 tables (2 extended + 16 new)

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

**Landing = PostgreSQL now** — one typed table per dataset (schema-on-write, columns mirror
`discovered_fields`), managed by the worker at ingest, reachable only through the
pipeline/dataset indirection so a later OLAP-engine swap is a localized worker+landing change,
never an API rewrite. `ingested_records` is the substrate-agnostic CDC op-log (business_key + op
+ provenance) so delete/lineage/idempotent-replay semantics are representable independent of the
typed table.

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
  storage, OLAP).
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
3. `[MI]` **Interim env/file secret resolver** on `aidw/sources/<id>/<key>` (probe R2).
- **0b (critical, from verify): live-OData fidelity probe** — point the `ENABLE_INAPI_EGRESS` path at ONE real public OData service (SAP ES5 / TripPin / Northwind V2+V4) and run parser(#1)+reconciler(#18) against its **live `$metadata` + one real data page**, asserting exact entity-set/field counts + one full discover→ingest cycle. Retires the load-bearing risk before any infra is built; costs only tokens on failure. Fixture tests stay as the CI net.

**Milestone 1 — connectivity config:** `[E]` `source_connection`, `source_credential`,
`odata_service_config` (+ each `source_id` FK as its own `[F+]`); `[F+]` `sources.is_enabled`,
`[F+]` `sources.last_test_status`.

**Milestone 2 — test one connection** 🟢 *first thin API⊥worker proof:* `[E]` `connection_test`
+ `[F+]` `source_id`; `[FF]` `POST /api/sources/{id}/test` (enqueue + interim exec:
anonymous/basic OData root GET, record status/latency/sanitized message).

**Milestone 3 — discover schema:** `[E]` `discovery_run` + `[F+]` `source_id`; the `datasets`
(4) and `discovered_fields` (7) discovery columns **as individual `[F+]` PRs**, the two
`first/last_seen_run_id` FKs each ordered **after `discovery_run` is merged**; `[FF]`
reconciliation module (UPSERT + tombstone, idempotent, 5 named test cases); `[FF]`
`POST /api/sources/{id}/discover`. **Schema-tier suggestions fire here** (see §6).

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

**Milestone 7 — breadth:** OAuth client-credentials; x509/mTLS `[MI]`; `delta_queue` +
snapshot-diff CDC strategies (worker-side `[MI]`/`[FF]` split); DB `information_schema` discovery
(reuses reconciler); `run_id` provenance FKs; LLM-narrative suggestion layer (opt-in, worker-side).

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

*Generated from a multi-agent design workflow + adversarial verification, 2026-07-05. Refile the
backlog items above as CodeAgent issues per milestone; the schema-discovery FK lineage
(`discovered_fields.dataset_id`) folds into Milestone 3.*
