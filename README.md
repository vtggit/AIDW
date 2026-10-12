# AIDW — AI Data Warehouse

AIDW is a self-hosted **data-warehouse and data-governance** platform. It connects to source
systems over OData, discovers their schema, ingests data, and applies governance to what it
holds.

What it does:

- **Sources and discovery** — register OData sources and connections, test them, and discover
  datasets and fields.
- **Ingestion** — pipelines with cursor-based change data capture, run either in the API process
  or by a separate worker, and load sequences that run pipelines in order on a schedule.
- **Profiling and PII** — profile fields and flag likely PII for a reviewer to confirm or dismiss.
- **Retention** — retention policies and sweeps.
- **Right-to-be-forgotten (RTBF)** — deletion requests with verification, erasure, and suppression
  so an erased subject is not re-ingested.
- **Dashboards** — dashboards built from suggested items, with charts and drill-down.
- **Processes** — process definitions with generated BPMN.
- **OData v4 feed** — exposes ingested datasets to spreadsheet and BI clients, authenticated with
  feed keys.
- **Audit** — an audit history of changes.

The web app has two pages: the dashboards view (`app/index.html`) and Studio
(`app/studio.html`), where sources, ingestion, governance and feed keys are configured.

An AI assistant panel can be attached to the app. It is served by a separate Assistant service
that is not part of this repository; without it the panel is simply not shown.

> AIDW is development and demonstration software. It is not intended for production use.

## License — free to view and use, not for redistribution or modification

AIDW is published under the **AIDW Evaluation and Reference License**. See [LICENSE](LICENSE) for
the full terms; the summary below does not replace them.

- ✅ **View and use** — you may view this repository and use the software for your own internal
  purposes, free of charge.
- ❌ **No redistribution** — do not distribute, publish, mirror, sublicense, sell, rent, lease, or
  offer it as a hosted or managed service.
- ❌ **No modification** — do not modify it or create derivative works.
- ❌ **Keep the notices** — do not remove or alter the license or copyright notices.
- ⚠️ **No warranty, no support** — the software is provided "as is", with no warranty and no
  support, maintenance or service commitment.

This is a **proprietary** license, **not** an open-source license. All rights are reserved by
Virtual Technology Group LLC.

> Note on forks: GitHub lets users fork a public repository, and the License permits that only to
> the extent the hosting platform's terms require it. A fork grants no further rights: the License
> still does not permit redistribution or modification.

## Running AIDW

AIDW runs as containers via Docker Compose: a PostgreSQL database, a FastAPI backend, and an
nginx-served frontend.

```bash
cp .env.example .env     # then change DB_PASSWORD
docker compose up -d --build
```

- The app is served at `http://localhost:8080`; nginx proxies `/api/` to the backend.
- The backend port (9000) is published on loopback only by default.
- The default configuration uses development authentication: a shared bearer token set by
  `AUTH_DEV_TOKEN`. To use an OpenID Connect identity provider instead, set `AUTH_MODE=production`
  and the `AUTH_*` variables.
- Ingestion runs in the API process by default and needs `ENABLE_INAPI_EGRESS=true` to reach
  source systems. To run it in the separate worker instead, set `INGEST_EXECUTOR=worker` and
  start the stack with `docker compose --profile worker up -d`.

`.env.example` documents the variables Docker Compose reads. The backend's configuration, API
and tests are described in [backend/README.md](backend/README.md).

## Repository layout

| Path | Contents |
|------|----------|
| `app/` | Frontend: static HTML, CSS and vanilla JavaScript served by nginx; Playwright specs in `app/tests/` |
| `backend/` | FastAPI backend, Alembic migrations, pytest suite, committed OpenAPI contract |
| `docs/` | [Behavioral architecture](docs/BEHAVIORAL-ARCHITECTURE.md), [design system](docs/design/design-system.md), [compliance controls](docs/compliance/CONTROLS.md) |
| `config/` | Product vision and deployment facts used by the build pipeline |
| `scripts/` | OpenAPI export, release-metadata check, and the [contract merge-gate](scripts/ca_gate/README.md) |
| `docker-compose.yml`, `.env.example` | Stack definition and its environment template |

## Contact

For questions about AIDW or its license, contact Virtual Technology Group LLC.
