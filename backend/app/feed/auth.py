"""Feed credential authentication dependency.

Exposes :func:`require_feed_credential`, a FastAPI dependency that authenticates
machine-to-machine feed consumers against the ``feed_credentials`` table.

Two presentation forms are accepted:

* ``Authorization: Basic base64(principal:key)`` — the principal must match the
  credential's stored ``principal`` and the key must match its ``key_hash``.
* ``X-Api-Key: <key>`` — the key must match a credential's ``key_hash``.

A valid ``X-Api-Key`` authenticates on its own even when an unrelated
(non-Basic) ``Authorization`` header is also present; a valid Basic
``Authorization`` header still authenticates.  Only the SHA-256 hex digest of
the presented key is ever computed; the plaintext key is never logged or
echoed.  Any missing, malformed, unknown, mismatched, or revoked credential
yields a 401 with a ``WWW-Authenticate`` challenge.  A malformed stored
``key_hash`` (e.g. a non-ASCII value) is treated as a non-match rather than
raising, so it 401s instead of 500ing.
"""

import base64
import binascii
import hashlib
import hmac
import logging

from fastapi import HTTPException, Request, status

from app.db.connection import get_cursor

logger = logging.getLogger(__name__)

_WWW_AUTHENTICATE = "Basic realm=" + chr(34) + "AIDW feed" + chr(34)


def _unauthorized() -> HTTPException:
    """Build the canonical 401 response for a failed feed credential check."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing feed credential.",
        headers={"WWW-Authenticate": _WWW_AUTHENTICATE},
    )


def _parse_basic_authorization(authorization: str) -> tuple[str, str] | None:
    """Decode an ``Authorization: Basic ...`` header into ``(principal, key)``.

    Returns ``None`` when the header is not a well-formed Basic credential.
    """
    parts = authorization.split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(parts[1].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    principal, key = decoded.split(":", 1)
    return principal, key


def _hash_matches(stored_hash, key_digest: str) -> bool:
    """Return True when a stored ``key_hash`` matches the presented key digest.

    Tolerates a malformed stored value (``None`` or a non-ASCII string that
    cannot be encoded to bytes): such a value is treated as a non-match rather
    than raising, so a corrupted row 401s instead of 500ing.
    """
    if stored_hash is None:
        return False
    try:
        stored_bytes = stored_hash.encode("utf-8")
    except (AttributeError, UnicodeEncodeError, TypeError):
        return False
    return hmac.compare_digest(stored_bytes, key_digest.encode("utf-8"))


def require_feed_credential(request: Request) -> dict:
    """Authenticate a feed consumer and return the matched credential row.

    Accepts either ``Authorization: Basic base64(principal:key)`` or
    ``X-Api-Key: <key>``.  A valid ``X-Api-Key`` authenticates even when an
    unrelated (non-Basic) ``Authorization`` header is also present; a valid
    Basic ``Authorization`` header still authenticates.  The SHA-256 hex digest
    of the presented key is compared (via :func:`hmac.compare_digest`) against
    the ``key_hash`` of non-revoked ``feed_credentials`` rows; for Basic auth
    the row's ``principal`` must also equal the presented username.  A ``NULL``
    or malformed ``key_hash`` never matches.

    Raises:
        HTTPException: 401 with a ``WWW-Authenticate`` challenge on any
            missing, malformed, unknown, mismatched, or revoked credential.

    Returns:
        The matched ``feed_credentials`` row as a dict.
    """
    authorization = request.headers.get("Authorization")
    api_key = request.headers.get("X-Api-Key")

    principal: str | None = None
    key: str | None = None

    if authorization:
        parsed = _parse_basic_authorization(authorization)
        if parsed is not None:
            principal, key = parsed
        elif api_key:
            # A non-Basic Authorization header is ignored when a valid
            # X-Api-Key is also presented.
            key = api_key
        else:
            raise _unauthorized()
    elif api_key:
        key = api_key
    else:
        raise _unauthorized()

    if not key:
        raise _unauthorized()

    key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()

    with get_cursor() as cur:
        if principal is not None:
            cur.execute(
                "SELECT id, name, principal, key_hash, key_prefix, revoked, "
                "created_at, updated_at "
                "FROM feed_credentials "
                "WHERE revoked IS NOT TRUE AND principal = %s",
                (principal,),
            )
        else:
            cur.execute(
                "SELECT id, name, principal, key_hash, key_prefix, revoked, "
                "created_at, updated_at "
                "FROM feed_credentials "
                "WHERE revoked IS NOT TRUE",
            )
        rows = cur.fetchall()

    for row in rows:
        if _hash_matches(row.get("key_hash"), key_digest):
            return dict(row)

    raise _unauthorized()
