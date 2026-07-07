"""Profile-tier re-scoring.

After the interim profiler writes ``field_profiles``, this pass revisits each still-``suggested``
suggestion and adjusts its score using REAL cardinality/fill — the thing the schema tier could only
guess at. It is the second half of the two-tier design: schema-tier proposes at low confidence,
profile-tier confirms or demotes once a data sample exists.

Scoring (only suggestions with a dimension or measure binding are re-scored; generic row-count KPIs
and detail tables keep their schema-tier score):

* dimension — confirmed low-arity categorical (distinct <= 25 and distinct/rows < 0.5) is exactly
  what a bar/pie wants, so it is boosted; a near-unique field (distinct/rows >= 0.6) is a poor
  dimension (a bar of ~unique values) and is demoted hard; anything between gets a middling score.
* measure — scaled by fill rate (non-null / rows), so a mostly-populated measure ranks above a
  sparse one.

Re-scored suggestions are marked ``strategy='profile'``. User decisions (accepted/dismissed) and
schema-drifted (stale) rows are never touched.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_cursor


def profile_score(base_score, fields: list[dict]) -> float | None:
    """Compute a profile-tier score from a suggestion's schema-tier ``base_score`` and its bound
    fields (each a dict with ``field_role`` + that field's profile counts, ``row_count`` None if it
    has no profile yet). Returns None when there is nothing data-dependent to score (leave as-is).
    """
    base = base_score if base_score is not None else 0.5
    dim = next(
        (
            f
            for f in fields
            if f.get("field_role") == "dimension" and f.get("row_count")
        ),
        None,
    )
    measure = next(
        (f for f in fields if f.get("field_role") == "measure" and f.get("row_count")),
        None,
    )
    if dim is None and measure is None:
        return None

    score = base
    if dim is not None:
        rows = dim["row_count"] or 0
        distinct = dim.get("distinct_count") or 0
        ratio = distinct / rows if rows else 1.0
        if distinct <= 25 and ratio < 0.5:
            score = 0.82  # confirmed low-arity categorical
        elif ratio >= 0.6:
            score = 0.12  # near-unique — a poor bar/pie dimension
        else:
            score = 0.45
    if measure is not None:
        rows = measure["row_count"] or 0
        nulls = measure.get("null_count") or 0
        fill = (rows - nulls) / rows if rows else 0.0
        score = max(score, 0.45 + 0.35 * fill)

    return round(min(max(score, 0.0), 1.0), 3)


def rescore_for_source(source_id: str) -> dict:
    """Re-score every still-``suggested`` suggestion of a source from its fields' profiles."""
    now = datetime.now(timezone.utc)
    rescored = 0
    with get_cursor() as cur:
        cur.execute("SELECT id FROM datasets WHERE source_id = %s", (source_id,))
        dataset_ids = [r["id"] for r in cur.fetchall()]
        if not dataset_ids:
            return {"suggestions_rescored": 0}

        cur.execute(
            "SELECT id, score FROM suggestions "
            "WHERE dataset_id = ANY(%s) AND status = 'suggested'",
            (dataset_ids,),
        )
        suggestions = cur.fetchall()

        for s in suggestions:
            cur.execute(
                "SELECT sf.field_role, fp.row_count, fp.null_count, fp.distinct_count "
                "FROM suggestion_fields sf "
                "LEFT JOIN field_profiles fp ON fp.discovered_field_id = sf.discovered_field_id "
                "WHERE sf.suggestion_id = %s",
                (s["id"],),
            )
            fields = [dict(r) for r in cur.fetchall()]
            new_score = profile_score(s["score"], fields)
            if new_score is None:
                continue
            cur.execute(
                "UPDATE suggestions SET score = %s, strategy = 'profile', updated_at = %s "
                "WHERE id = %s",
                (new_score, now, s["id"]),
            )
            rescored += 1

    return {"suggestions_rescored": rescored}
