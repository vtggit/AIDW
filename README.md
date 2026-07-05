# AIDW — AI Data Warehouse

A self-hosted, AI-operated data warehouse, built and operated by its own **CodeAgent** instance
(instance-per-product; the AICRM sibling runs the same CodeAgent code against `vtggit/AICRM`).

## Bootstrap provenance

This repo was **scaffolded from the AICRM structural skeleton** — the proven CodeAgent-idiom
backend (FastAPI + raw-psycopg2 `*PostgresRepository` classes + Alembic head-chained migrations
+ a pytest `conftest` harness + the `scripts/ca_gate/` merge gate + CI). That guarantees the
deterministic recipe lanes apply immediately (see the CodeAgent `docs/PRODUCT-INTEGRATION.md`).

The seed carries the AICRM example entities as **idiom exemplars**; the real AIDW domain
(sources, datasets, pipelines, runs) is grown by CodeAgent and organically replaces them. This
is the "scaffold-first, then let the recipes build" pattern.

## Operating model

- Issues labeled `ca-deliberate` are deliberated by the CodeAgent panel, answered (operator or
  auto-operator, steered by `config/product_vision.md` + `config/product_facts.md`), built to a
  DRAFT PR, and merged by a human. CodeAgent never merges.
- The build gate (`scripts/ca_gate/check_pr_contract.py`) runs locally identically to CI.
