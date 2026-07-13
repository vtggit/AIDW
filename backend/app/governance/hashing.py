"""Suppression key hashing (RTBF, governance #76).

subject_key_hash is THE bridge between erasure and re-ingest suppression: deterministic (the
ingest filter must reproduce it exactly), non-attributable without the pepper (business keys
are low-entropy — plain SHA-256 would be dictionary-reversible), and dataset-scoped (the
dataset_id is folded into the HMAC input, so the single key_hash column is globally unique
with no composite index).

The pepper is read at CALL time from AIDW_SUPPRESSION_PEPPER — never at import, so tests and
workers control it per-process — and is never stored in the database. Rotation orphans every
suppression entry (#76 custody rule): guard the pepper like a database backup.
"""

import hashlib
import hmac
import os

_ENV = "AIDW_SUPPRESSION_PEPPER"
_KEY_MAX = (
    255  # mirrors app/ingest/mapper business_key cap — erased key and re-ingested twin
)
#                 must hash identically


def subject_key_hash(dataset_id: str, business_key: str) -> str:
    """hex(HMAC-SHA256(pepper, dataset_id || 0x00 || business_key[:255]))."""
    pepper = os.environ.get(_ENV)
    if not pepper:
        raise RuntimeError(
            f"{_ENV} environment variable is not set — the suppression pepper is required "
            f"for RTBF hashing (see governance #76 for provisioning and custody)"
        )
    msg = dataset_id.encode() + b"\x00" + business_key[:_KEY_MAX].encode()
    return hmac.new(pepper.encode(), msg, hashlib.sha256).hexdigest()
