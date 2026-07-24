# AIDW — AI Data Warehouse

AIDW is a self-hosted **data-governance and discovery** platform. It helps teams connect data
sources, profile datasets and detect PII, manage data-retention policies, handle
right-to-be-forgotten (RTBF) erasure requests, define and generate processes (BPMN), and build
dashboards — with an in-app **AI assistant** for querying the data, navigating the app, and
proposing changes.

## License — free to use, not for redistribution or modification

AIDW is **free to download and use**, but it **may not be redistributed or modified**. See
[LICENSE](LICENSE) for the full terms.

- ✅ **Use** — download and use the software for your own use, free of charge.
- ❌ **No redistribution** — do not distribute, publish, sublicense, sell, host for others, or
  otherwise share it with third parties.
- ❌ **No modification** — do not modify it or create derivative works, including forks intended for
  modification or redistribution.

This is a **proprietary** license, **not** an open-source license. All rights not expressly granted
are reserved by Virtual Technology Group.

> Note on forks: making a repository public on GitHub lets other GitHub users use the platform's
> fork feature, but this License still governs what may lawfully be done with the code — and it does
> not permit redistribution or modification.

## Running AIDW

AIDW runs as a set of containers via Docker Compose (a PostgreSQL database, a FastAPI backend, and
an nginx-served frontend). Configure the environment from `.env.example` and start the stack with
`docker compose up -d`.

## Support

For questions about AIDW or its license, contact Virtual Technology Group.
