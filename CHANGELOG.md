# Changelog

All notable changes to AIDW are recorded here. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/), and versions follow semantic
versioning (see the `VERSION` file).

Domain changes are delivered incrementally by the CodeAgent pipeline; user-facing
entries are grouped here under `[Unreleased]` until a version is cut.

## [Unreleased]

This section summarises everything shipped since 0.2.3. It was rebuilt from the code on
2026-11-02; individual changes are in the Git history.

### Added

- **Connectivity and discovery:** sources, connections, credentials and OData service
  configuration; connection tests; schema discovery over OData into datasets and discovered
  fields, with discovery-run lineage (`/api/sources`, `/api/datasets`,
  `/api/discovered-fields`, `/api/discovery-runs`).
- **Ingestion:** pipelines and runs with cursor-based change data capture, ingested records and
  raw payloads, and a separate worker service (`INGEST_EXECUTOR=worker`,
  `docker compose --profile worker`) that also reaps stale runs.
- **Load sequences:** ordered pipeline steps, run history, manual execution and worker-fired
  `hourly`, `daily` or `weekly` schedules, with a generated BPMN view
  (`/api/load-sequences/{id}/bpmn`).
- **Dashboards:** schema-tier and profile-tier suggestions with accept and dismiss, dashboards
  built from accepted items, charts and drill-down, an admin layout editor and per-user tile
  layouts (`/api/suggestions`, `/api/dashboards`, `/api/dashboard-items`,
  `/api/dashboard-item-layouts`).
- **Profiling and PII:** field profiles and PII flags with reviewer confirm and dismiss; flagged
  fields have their values withheld from profiles and charts (`/api/pii-flags`).
- **Retention:** retention policies and admin-run purge sweeps (`/api/retention-policies`).
- **Right to be forgotten:** deletion requests with verification, erasure and a suppression list
  that stops an erased subject from being re-ingested or re-profiled
  (`/api/deletion-requests`).
- **Processes:** process definitions, steps and flows, a Process wizard, server-side BPMN XML and
  SVG generation, and a non-mutating validate endpoint (`/api/process-definitions`).
- **OData v4 feed:** ingested datasets exposed to spreadsheet and BI clients with feed keys that
  record when they were last used (`/api/feed/v4`, `/api/feed-credentials`).
- **Workflow engine proxy:** `/api/workflows` starts and reads processes on an optional Flowable
  engine.
- **Web app:** the Dashboards and Studio pages, with Studio's tools for data sources, suggestions,
  PII flags, the Process wizard, load sequences, retention, ingestion, feed keys and audit
  history; an optional assistant panel and deep links.
- **Audit:** an audit history of changes, visible to admins (`/api/audit`), and a second log
  written by most changes (`/api/audit-logs`).
- **Authentication:** an OpenID Connect login flow in the web app (`AUTH_MODE=production`).
- **Egress controls:** outbound calls validate their destination and fail closed; an optional
  strict policy also denies loopback targets (`EGRESS_POLICY`).
- **Engineering:** pinned dependency versions (`backend/constraints.txt`), the contract merge
  gate with its daily re-validation, and a Docs check for Markdown changes.
- Behavioral-layer architecture spec (`docs/BEHAVIORAL-ARCHITECTURE.md`).

### Changed

- A failed ingestion run, retention sweep or erasure stores only the error's type and database
  error code for any error that could carry data.
- The backend port is published on loopback only by default (`BACKEND_BIND_HOST`), with per-process
  memory ceilings and an optional database statement timeout.

### Removed

- The vendored bpmn-js canvas: the Process wizard and the server-side generator replaced it (see
  `docs/compliance/adoptions/bpmn-js.md`).

## [0.2.3] - 2026-07-05

### Added

- Warehouse-infrastructure skeleton: health, auth, and audit routers with an
  append-only `audit_log` baseline migration.
- CodeAgent build integration and CI onboarding (quality, security-hygiene, and
  release-metadata gates wired for this product).
