"""The connector/ingestion worker (Milestone 6, doc §1/§8).

Claims pending ingestion runs from the ``runs`` spine with ``FOR UPDATE SKIP LOCKED`` and
executes them through the SAME ``app.ingest.service`` logic the interim in-API executor uses —
identical rows either way, so the API and worker paths stay interchangeable. The process
entrypoint is ``python -m app.worker``; deploying the always-on process is operator infra.
"""
