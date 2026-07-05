# Changelog

All notable changes to AIDW are recorded here. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/), and versions follow semantic
versioning (see the `VERSION` file).

Domain changes are delivered incrementally by the CodeAgent pipeline; user-facing
entries are grouped here under `[Unreleased]` until a version is cut.

## [Unreleased]

### Added

- `sources` entity — configured connections to source systems (CRUD at `/api/sources`).
- `datasets` entity — discovered tables/objects from a source (CRUD at `/api/datasets`).
- `datasets.source_id` — nullable FK to `sources(id)` (`ON DELETE SET NULL`, indexed):
  lineage recording which source a dataset was discovered from.

## [0.2.3] - 2026-07-05

### Added

- Warehouse-infrastructure skeleton: health, auth, and audit routers with an
  append-only `audit_log` baseline migration.
- CodeAgent build integration and CI onboarding (quality, security-hygiene, and
  release-metadata gates wired for this product).
