# AIDW — AI Data Warehouse

AIDW is a self-hosted **data-warehouse and data-governance** platform. It connects to source
systems over OData, discovers their schema, ingests data, and applies governance to what it
holds.

What it does:

- **Sources and discovery** — register OData sources and connections, test them, and discover
  datasets and fields.
- **Ingestion** — pipelines with cursor-based change data capture, run either in the API process
  or by a separate worker. Load sequences run pipelines in step order, on demand or on a
  schedule; scheduled runs are fired by the worker. The worker also finishes off a run whose
  executor stopped mid-run, so an interrupted run does not block its sequence's schedule.
- **Profiling and PII** — profile fields and flag likely PII for a reviewer to confirm or dismiss.
- **Retention** — retention policies and sweeps.
- **Right-to-be-forgotten (RTBF)** — deletion requests with verification, erasure, and suppression
  so an erased subject is not re-ingested. Deletion requests are handled through the API.
- **Failure details without data** — a failed ingestion run, retention sweep or erasure stores
  only the error's type and database error code for any error that could carry data, so source
  values in a database error are not stored or shown.
- **Dashboards** — dashboards built from suggested items, with charts, drill-down and an
  admin layout editor.
- **Processes** — process definitions with generated BPMN (XML and SVG); load sequences can also
  be shown and downloaded as BPMN.
- **OData v4 feed** — exposes ingested datasets to spreadsheet and BI clients, authenticated with
  feed keys. Each key records when it was last used.
- **Audit** — an audit history of changes, visible to admins.

The web app has two pages: Dashboards (`app/index.html`) and Studio (`app/studio.html`). Studio
shows one tool at a time: Data sources, Suggested dashboard items, PII flags, Process wizard,
Load sequences, Data retention, Ingestion, Feed keys and Audit history. Feed keys and Audit
history are admin-only, and so are actions such as Discover, Run now, retention sweeps and key
rotation or revocation. The run lists show readable times, how long a finished run took, and
how long a running one has been going. The Feed keys tool marks keys not used for 90 days.

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
nginx-served frontend. `docker compose up` also starts a throwaway test database (`test-db`,
host port 5433, no volume) that the backend test runner uses.

```bash
cp .env.example .env     # then change DB_PASSWORD
docker compose up -d --build
```

- The app is served at `http://localhost:8080`; nginx proxies `/api/` to the backend and tells
  browsers to revalidate files on every load, so a redeploy is picked up without a hard reload.
- The backend port (9000) is published on loopback only by default. The database port (5432) is
  published on all interfaces unless you change `DB_PORT_HOST` or the compose file.
- The default configuration uses development authentication: a shared bearer token set by
  `AUTH_DEV_TOKEN`, with the roles in `AUTH_DEV_ROLES` (default `user`; set `admin,user` to see
  the admin tools). To use an OpenID Connect identity provider instead, set
  `AUTH_MODE=production` and the `AUTH_*` variables.
- Ingestion runs in the API process by default and needs `ENABLE_INAPI_EGRESS=true` to reach
  source systems. To run it in the separate worker instead, set `INGEST_EXECUTOR=worker` and
  start the stack with `docker compose --profile worker up -d`. Scheduled load sequences only
  fire when the worker is running.
- Executing a deletion request needs `AIDW_SUPPRESSION_PEPPER`, set to the same value for the
  backend and the worker and never changed afterwards; `.env.example` explains why.
- The backend reports the version in the repository's `VERSION` file, which Compose mounts into
  the container.

`.env.example` documents the variables Docker Compose reads. The backend's configuration, API
and tests are described in [backend/README.md](backend/README.md).

## Repository layout

| Path | Contents |
|------|----------|
| `app/` | Frontend: static HTML, CSS and vanilla JavaScript served by nginx; Playwright specs in `app/tests/` |
| `backend/` | FastAPI backend, Alembic migrations, pytest suite, committed OpenAPI contract, pinned dependency versions (`constraints.txt`) |
| `docs/` | [Behavioral architecture](docs/BEHAVIORAL-ARCHITECTURE.md), [design system](docs/design/design-system.md), [compliance controls](docs/compliance/CONTROLS.md), [merge-gate required checks](docs/branch-protection.md) |
| `config/` | Product vision, deployment facts and compliance capabilities used by the build pipeline |
| `scripts/` | OpenAPI export, release-metadata check, dependency-pin refresh (`refresh_constraints.sh`), and the [contract merge-gate](scripts/ca_gate/README.md) |
| `tests/` | Tests for the merge-gate scripts (`tests/ca_gate/`) |
| `.github/workflows/` | Backend CI, the contract merge-gate, and its daily re-validation |
| `docker-compose.yml`, `.env.example` | Stack definition and its environment template |
| `VERSION`, `CHANGELOG.md` | Release version and change log |

## Contact

For questions about AIDW or its license, contact Virtual Technology Group LLC.
