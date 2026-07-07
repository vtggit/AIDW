"""Interim data profiling (schema-tier -> profile-tier).

``service`` fetches a sampled data page per dataset via the in-API egress, computes per-field
statistics (row/null/distinct counts, min/max, most-common) into ``field_profiles``, then triggers
the profile-tier re-score (``app.suggestion.rescore``) so suggestions gain REAL cardinality/fill
confidence. This is the doc's interim profiler — it runs before the dedicated ingestion worker
exists, over a sample rather than a full ingest.
"""
