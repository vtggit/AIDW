"""OData schema-discovery orchestration (interim in-API egress path).

Loads a source's connection config, fetches its OData ``$metadata`` (anonymous/basic sources only
for now — the connector worker takes egress over later), reads it with the deterministic reader,
and UPSERTS datasets + discovered_fields with lineage. Idempotent: a re-run matches existing rows
by natural key (source_id+name for datasets, dataset_id+name for fields), so discovery can run
repeatedly without duplicating.
"""

import urllib.request
from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor
from app.discovery.schema_reader import get_reader


class DiscoveryError(Exception):
    """A discovery precondition failed (e.g. the source has no connection endpoint)."""


def _fetch_metadata(url: str) -> bytes:
    """Fetch the raw $metadata document. Factored out so tests can substitute a fixture without
    hitting the network."""
    return urllib.request.urlopen(url, timeout=30).read()


def discover_source(source_id: str) -> dict:
    """Discover the schema of one source into datasets/discovered_fields. Raises LookupError if the
    source doesn't exist, DiscoveryError if it isn't discoverable."""
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
    metadata_path = ((odata or {}).get("metadata_path") or "$metadata").lstrip("/")
    url = conn["endpoint"].rstrip("/") + "/" + metadata_path

    reader = get_reader(source.get("type") or "odata")
    datasets = reader.read(_fetch_metadata(url))

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
                        "UPDATE discovered_fields SET data_type = %s, updated_at = %s "
                        "WHERE dataset_id = %s AND name = %s",
                        (f.data_type, now, ds_id, f.name),
                    )
                    updated_f += 1
                else:
                    cur.execute(
                        "INSERT INTO discovered_fields (id, name, data_type, dataset_id, "
                        "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
                        (str(uuid4()), f.name, f.data_type, ds_id, now, now),
                    )
                    created_f += 1

    return {
        "source_id": source_id,
        "datasets_discovered": len(datasets),
        "fields_discovered": sum(len(d.fields) for d in datasets),
        "datasets_created": created_ds,
        "fields_created": created_f,
        "fields_updated": updated_f,
    }
