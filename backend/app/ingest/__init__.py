"""Cursor-pattern CDC ingest (interim in-API executor).

Composed of three small fixture-testable modules per docs/BEHAVIORAL-ARCHITECTURE.md §5
Milestone 4: ``mapper`` (OData page → rows + business keys), ``filters`` (``$filter`` URL from a
watermark), ``cursor`` (cursor-advance + run-count transaction). ``service`` composes them behind
``POST /api/pipelines/{id}/runs``; the Milestone 6 worker will run the same modules unchanged.
"""
