"""OData schema-discovery orchestration (interim in-API egress path).

Loads a source's connection config, fetches its OData ``$metadata`` (anonymous/basic sources only
for now — the connector worker takes egress over later), reads it with the deterministic reader,
and UPSERTS datasets + discovered_fields with lineage. Idempotent: a re-run matches existing rows
by natural key (source_id+name for datasets, dataset_id+name for fields), so discovery can run
repeatedly without duplicating.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.discovery.schema_reader import get_reader
from app.egress.http import (
    EgressAuthError,
    EgressError,
    SecretRefInvalidAuthError,
    SecretUnavailableAuthError,
    fetch_bytes,
    resolve_fetch_timeout,
)
from app.egress.policy import EgressDestinationDenied
from app.pii.service import scan_pii_for_source
from app.suggestion.service import regenerate_suggestions_for_source

logger = logging.getLogger(__name__)


class DiscoveryError(Exception):
    """A discovery precondition failed (e.g. the source has no connection endpoint)."""


def _fetch_timeout_for(conn: dict) -> int | None:
    """The connection's fetch timeout: None when ``timeout_seconds`` is NULL,
    else the stored value validated against 1-600. Raises DiscoveryError
    naming the ``timeout_seconds`` field for a stored value out of range."""
    stored = conn.get("timeout_seconds")
    if stored is None:
        return None
    try:
        return resolve_fetch_timeout(stored)
    except ValueError as exc:
        raise DiscoveryError(str(exc)) from exc


def _fetch_metadata(url: str, timeout: int = 30) -> bytes:
    """Fetch the raw $metadata document. Factored out so tests can substitute a fixture without
    hitting the network."""
    try:
        return fetch_bytes(url, timeout=timeout)
    except (SecretUnavailableAuthError, SecretRefInvalidAuthError) as exc:
        raise DiscoveryError("credential unavailable for this source") from exc
    except EgressAuthError as exc:
        raise DiscoveryError("authentication against the source failed") from exc
    except EgressDestinationDenied as exc:
        raise DiscoveryError("destination denied by egress policy") from exc
    except (EgressError, TimeoutError, ConnectionError) as exc:
        raise DiscoveryError("source endpoint unreachable") from exc


def _select_entity_sets(datasets: list, entity_sets: list[str]) -> list:
    """Restrict the read entity sets to the requested names, in the order the reader read them.
    Raises ValueError naming every requested name absent from the metadata, before the caller
    has written anything."""
    available = {d.name for d in datasets}
    missing = [n for n in dict.fromkeys(entity_sets) if n not in available]
    if missing:
        raise ValueError(
            "entity sets not found in source $metadata: " + ", ".join(missing)
        )
    wanted = set(entity_sets)
    return [d for d in datasets if d.name in wanted]


def discover_source(source_id: str, entity_sets: list[str] | None = None) -> dict:
    """Discover the schema of one source into datasets/discovered_fields.

    ``entity_sets`` optionally restricts the run to the named entity sets of the source's
    ``$metadata``: only those sets get datasets/discovered_fields rows, and the response
    counts report only those sets. A requested name absent from the metadata raises ValueError
    naming every missing name, before anything is written. Omitted, behaviour is unchanged
    (every set of the source).

    Raises LookupError if the source doesn't exist, DiscoveryError if it isn't discoverable.
    """
    with get_cursor() as cur:
        cur.execute("SELECT * FROM sources WHERE id = %s", (source_id,))
        source = cur.fetchone()
        if source is None:
            raise LookupError("source not found")
        cur.execute(
            "SELECT * FROM source_connections WHERE source_id = %s "
            "ORDER BY created_at LIMIT 1",
            (source_id,),
        )
        conn = cur.fetchone()
        cur.execute(
            "SELECT * FROM odata_service_configs WHERE source_id = %s "
            "ORDER BY created_at LIMIT 1",
            (source_id,),
        )
        odata = cur.fetchone()

    if conn is None or not (conn.get("endpoint") or "").strip():
        raise DiscoveryError("source has no source_connections endpoint to discover")
    if entity_sets is not None and not entity_sets:
        raise ValueError("entity_sets must not be empty")
    fetch_timeout = _fetch_timeout_for(conn)
    metadata_path = ((odata or {}).get("metadata_path") or "$metadata").lstrip("/")
    url = conn["endpoint"].rstrip("/") + "/" + metadata_path

    reader = get_reader(source.get("type") or "odata")
    if fetch_timeout is None:
        datasets = reader.read(_fetch_metadata(url))
    else:
        datasets = reader.read(_fetch_metadata(url, timeout=fetch_timeout))
    if entity_sets is not None:
        datasets = _select_entity_sets(datasets, entity_sets)

    now = datetime.now(timezone.utc)
    created_ds = created_f = updated_f = 0
    with get_cursor() as cur:
        for d in datasets:
            cur.execute(
                "SELECT id FROM datasets WHERE source_id = %s AND name = %s",
                (source_id, d.name),
            )
            row = cur.fetchone()
            if row:
                ds_id = row["id"]
            else:
                ds_id = str(uuid4())
                cur.execute(
                    "INSERT INTO datasets (id, name, object_type, source_id, "
                    "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (ds_id, d.name, d.object_type, source_id, now, now),
                )
                created_ds += 1
            for f in d.fields:
                cur.execute(
                    "SELECT id FROM discovered_fields WHERE dataset_id = %s AND name = %s",
                    (ds_id, f.name),
                )
                if cur.fetchone():
                    cur.execute(
                        "UPDATE discovered_fields SET data_type = %s, is_nullable = %s, "
                        "is_key = %s, field_position = %s, updated_at = %s "
                        "WHERE dataset_id = %s AND name = %s",
                        (
                            f.data_type,
                            f.nullable,
                            f.is_key,
                            f.field_position,
                            now,
                            ds_id,
                            f.name,
                        ),
                    )
                    updated_f += 1
                else:
                    cur.execute(
                        "INSERT INTO discovered_fields (id, name, data_type, is_nullable, "
                        "is_key, field_position, dataset_id, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            str(uuid4()),
                            f.name,
                            f.data_type,
                            f.nullable,
                            f.is_key,
                            f.field_position,
                            ds_id,
                            now,
                            now,
                        ),
                    )
                    created_f += 1

    # Automatic trigger: regenerate schema-tier suggestions now that the schema is persisted.
    # Best-effort — a suggestion failure must never fail the discovery that already committed.
    suggestion_counts = {
        "suggestions_created": 0,
        "suggestions_revived": 0,
        "suggestions_staled": 0,
    }
    try:
        suggestion_counts = regenerate_suggestions_for_source(source_id)
    except Exception:
        logger.exception(
            "schema-tier suggestion regeneration failed for source %s (discovery still succeeded)",
            source_id,
        )

    # Automatic trigger: schema-tier PII watchdog scan (governance #75). Also best-effort — and
    # its retro-scrub closes the profile leak for any field newly flagged as PII.
    pii_counts = {
        "pii_flags_created": 0,
        "pii_flags_revived": 0,
        "pii_flags_upgraded": 0,
        "pii_flags_staled": 0,
        "profiles_redacted": 0,
    }
    try:
        pii_counts = scan_pii_for_source(source_id)
    except Exception:
        logger.exception(
            "PII watchdog scan failed for source %s (discovery still succeeded)",
            source_id,
        )

    return {
        "source_id": source_id,
        "datasets_discovered": len(datasets),
        "fields_discovered": sum(len(d.fields) for d in datasets),
        "datasets_created": created_ds,
        "fields_created": created_f,
        "fields_updated": updated_f,
        **suggestion_counts,
        **pii_counts,
    }
