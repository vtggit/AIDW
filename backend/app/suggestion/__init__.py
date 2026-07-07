"""Dashboard-suggestion engine (schema-tier).

``engine`` is a pure, deterministic rule pass over a dataset's discovered fields — no DB, no
network — so it is exhaustively testable. ``service`` persists/reconciles its output against the
``suggestions``/``suggestion_fields`` tables and is invoked automatically after a discovery run.
"""
