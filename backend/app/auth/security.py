# Token validation helpers
#
# This module owns the token → AuthUser translation.  Route-level code
# should never import this directly; always go through dependencies.py.
#
# Design intent
# -------------
# The public interface is the single function `validate_token(raw_token)`.
# Two modes are supported via ``AUTH_MODE``:
#
# * ``development`` → simple bearer-token comparison (safe for local dev)
# * ``production``  → real JWT validation against IdP JWKS
#
# The production path fetches JWKS from the configured IdP, caches the
# keys, verifies the JWT signature and claims, and normalises roles/
# groups from the decoded payload into ``AuthUser``.

import logging
import time
from functools import lru_cache
from typing import Any

import jwt  # pyjwt
import requests

from app.auth.config import (
    AUTH_ALGORITHMS,
    AUTH_AUDIENCE,
    AUTH_CLIENT_ID,
    AUTH_DEV_ROLES,
    AUTH_DEV_TOKEN,
    AUTH_GROUP_CLAIMS,
    AUTH_ISSUER,
    AUTH_JWKS_CACHE_TTL,
    AUTH_JWKS_URL,
    AUTH_MODE,
    AUTH_ROLE_CLAIMS,
)
from app.auth.models import AuthUser
from app.observability.logging import get_request_id

logger = logging.getLogger(__name__)


def _req() -> str:
    """Return a request-ID prefix for log lines, or empty string."""
    rid = get_request_id()
    return f" request_id={rid}" if rid else ""


# ---------------------------------------------------------------------------
# Public interface — the ONLY function callers should use
# ---------------------------------------------------------------------------


def validate_token(raw_token: str) -> AuthUser | None:
    """
    Validate *raw_token* and return an ``AuthUser`` on success, or
    ``None`` when the token is missing / expired / malformed.

    The implementation is selected by ``AUTH_MODE``:

    * ``development`` → simple bearer-token comparison (safe for local dev)
    * ``production``  → real JWT validation against IdP JWKS

    Any other value for ``AUTH_MODE`` is treated as a configuration error
    and fails closed (returns ``None``).
    """
    if not raw_token:
        logger.warning("auth: missing or empty token%s", _req())
        return None

    if AUTH_MODE == "production":
        return _validate_token_jwt(raw_token)
    if AUTH_MODE == "development":
        return _validate_token_dev(raw_token)

    # Fail closed for unknown modes — a typo like "prod" or "staging"
    # should never silently fall back to dev-token behavior.
    logger.error("auth: unsupported AUTH_MODE=%s — failing closed%s", AUTH_MODE, _req())
    return None


# ---------------------------------------------------------------------------
# Development stub — intentionally simple, clearly marked for replacement
# ---------------------------------------------------------------------------


def _validate_token_dev(token: str) -> AuthUser | None:
    """
    Accept any non-empty bearer token that matches ``AUTH_DEV_TOKEN``.

    In development this lets you test the auth boundary without a real
    IdP.  The token value comes from the ``AUTH_DEV_TOKEN`` environment
    variable (default: ``dev-secret-token``).

    Supports optional role suffix for testing different identities:

        dev-secret-token        → uses AUTH_DEV_ROLES (default: ["user"])
        dev-secret-token:admin  → ["admin", "user"]
        dev-secret-token:user   → ["user"]
    """
    if not token:
        logger.warning("auth: missing or empty token%s", _req())
        return None

    # Check for role-suffixed dev token (e.g. "dev-secret-token:admin")
    base_token = AUTH_DEV_TOKEN
    if token == base_token:
        # Exact match — use configured default roles
        roles = AUTH_DEV_ROLES
        sub = "dev-user-1"
        username = "developer"
    elif token.startswith(base_token + ":"):
        # Role-suffixed token — extract requested role
        suffix = token[len(base_token) + 1 :]
        if suffix == "admin":
            roles = ["admin", "user"]
            sub = "dev-admin-1"
            username = "admin"
        elif suffix == "user":
            roles = ["user"]
            sub = "dev-user-1"
            username = "developer"
        else:
            logger.warning("auth: unknown dev token suffix '%s'%s", suffix, _req())
            return None
    else:
        logger.warning("auth: dev token mismatch%s", _req())
        return None

    return AuthUser(
        sub=sub,
        username=username,
        email=f"{username}@aicrm.local",
        roles=roles,
        groups=[],
        raw_claims={"mode": "development"},
    )


# ---------------------------------------------------------------------------
# Production JWT validation — real IdP integration
# ---------------------------------------------------------------------------


def _fetch_jwks() -> dict[str, Any]:
    """
    Fetch the JWKS document from the IdP.

    Returns the raw JWKS JSON (``{"keys": [...]}``).  Raises on network
    errors so the caller can fail closed.
    """
    logger.debug("Fetching JWKS from %s", AUTH_JWKS_URL)
    resp = requests.get(AUTH_JWKS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


# Cache JWKS for AUTH_JWKS_CACHE_TTL seconds.  The cache is keyed on a
# time-bucket so it automatically expires and refreshes.
@lru_cache(maxsize=1)
def _cached_jwks(_bucket: int) -> dict[str, Any]:
    return _fetch_jwks()


def _get_jwks() -> dict[str, Any]:
    """Return cached JWKS, refreshing when the TTL has elapsed."""
    bucket = int(time.time()) // AUTH_JWKS_CACHE_TTL
    try:
        return _cached_jwks(bucket)
    except ValueError:
        # Cache was invalidated — fetch fresh
        _cached_jwks.cache_clear()
        return _cached_jwks(bucket)


def _get_verification_key(jwks: dict[str, Any], header: dict[str, Any]) -> str | None:
    """
    Resolve the correct verification key from the JWKS set.

    Matches on ``kid`` (key ID).  Returns a PEM-encoded public key
    string that ``pyjwt`` can use for verification, or ``None`` when
    no matching key is found.
    """
    kid = header.get("kid")
    for key_entry in jwks.get("keys", []):
        if kid and key_entry.get("kid") != kid:
            continue
        pem = _jwk_to_pem(key_entry)
        if pem:
            return pem
    logger.warning("No matching key found in JWKS for kid=%s", kid)
    return None


def _jwk_to_pem(jwk: dict[str, Any]) -> str | None:
    """
    Convert a single JWK entry to a PEM-encoded public key string.

    Supports RSA (kty=RSA) and EC (kty=EC) keys, which cover the
    overwhelming majority of enterprise IdP deployments.
    """
    from base64 import urlsafe_b64decode

    kty = jwk.get("kty")

    if kty == "RSA":
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

            n = int.from_bytes(urlsafe_b64decode(jwk["n"] + "=="), "big")
            e = int.from_bytes(urlsafe_b64decode(jwk["e"] + "=="), "big")

            pub = rsa_mod.RSAPublicNumbers(e, n).public_key()
            return pub.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
        except Exception as exc:
            logger.error("Failed to convert RSA JWK to PEM: %s", exc)
            return None

    if kty == "EC":
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            crv = jwk.get("crv", "P-256")
            curve_map = {
                "P-256": ec.SECP256R1(),
                "P-384": ec.SECP384R1(),
                "P-521": ec.SECP521R1(),
            }
            curve = curve_map.get(crv)
            if not curve:
                logger.warning("Unsupported EC curve: %s", crv)
                return None

            x = urlsafe_b64decode(jwk["x"] + "==")
            y = urlsafe_b64decode(jwk["y"] + "==")

            pub = ec.EllipticCurvePublicNumbers(
                x=int.from_bytes(x, "big"),
                y=int.from_bytes(y, "big"),
                curve=curve,
            ).public_key()
            return pub.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
        except Exception as exc:
            logger.error("Failed to convert EC JWK to PEM: %s", exc)
            return None

    logger.warning("Unsupported JWK key type: %s", kty)
    return None


def _resolve_nested_claim(claims: dict[str, Any], path: str) -> Any:
    """
    Resolve a dot-notation claim path against the token payload.

    Supports ``{client_id}`` substitution so paths like
    ``resource_access.{client_id}.roles`` resolve correctly.
    """
    path = path.replace("{client_id}", AUTH_CLIENT_ID)
    parts = path.split(".")
    current: Any = claims
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _extract_string_list(value: Any) -> list[str]:
    """
    Normalise a claim value into a list of strings.

    Handles ``None``, plain strings, and lists of strings.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


def _normalize_roles(claims: dict[str, Any]) -> list[str]:
    """
    Scan the configured role claim paths and collect unique role strings.

    Returns a deduplicated, sorted list of normalised roles.
    """
    roles: list[str] = []
    for claim_path in AUTH_ROLE_CLAIMS:
        raw = _resolve_nested_claim(claims, claim_path)
        if isinstance(raw, dict) and "roles" in raw:
            # Keycloak resource_access returns {"roles": [...]}
            roles.extend(_extract_string_list(raw["roles"]))
        else:
            roles.extend(_extract_string_list(raw))
    # Deduplicate while preserving order
    seen: set = set()
    unique: list[str] = []
    for r in roles:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def _normalize_groups(claims: dict[str, Any]) -> list[str]:
    """
    Scan the configured group claim paths and collect unique group strings.
    """
    groups: list[str] = []
    for claim_path in AUTH_GROUP_CLAIMS:
        raw = _resolve_nested_claim(claims, claim_path)
        groups.extend(_extract_string_list(raw))
    seen: set = set()
    unique: list[str] = []
    for g in groups:
        if g not in seen:
            seen.add(g)
            unique.append(g)
    return unique


def _validate_token_jwt(raw_token: str) -> AuthUser | None:
    """
    Real JWT validation against the configured IdP.

    Steps:
    1. Unsign the JWT header to get ``kid``
    2. Fetch JWKS (cached) and locate the matching key
    3. Verify signature, issuer, audience, and expiry
    4. Normalise roles and groups from claims
    5. Return ``AuthUser`` — or ``None`` on any failure (fail closed)
    """
    try:
        # Step 1 — decode header without verification to get kid/alg
        header = jwt.get_unverified_header(raw_token)

        # Step 2 — fetch JWKS and find the right key
        jwks = _get_jwks()
        key = _get_verification_key(jwks, header)
        if key is None:
            logger.warning(
                "auth: JWT signature verification failed — no matching key in JWKS%s",
                _req(),
            )
            return None

        # Step 3 — decode and verify
        payload: dict[str, Any] = jwt.decode(
            raw_token,
            key,
            algorithms=AUTH_ALGORITHMS,
            audience=AUTH_AUDIENCE,
            issuer=AUTH_ISSUER,
            options={
                "require": ["exp", "sub"],
                "verify_exp": True,
                "verify_signature": True,
            },
        )

        # Step 4 — extract identity claims
        sub = payload.get("sub")
        if not sub:
            logger.warning("auth: JWT missing required 'sub' claim%s", _req())
            return None

        username = (
            payload.get("preferred_username")
            or payload.get("name")
            or payload.get("email")
        )

        # Step 5 — normalise roles and groups
        roles = _normalize_roles(payload)
        groups = _normalize_groups(payload)

        # Ensure every authenticated user has at least a baseline role
        if not roles:
            roles = ["user"]

        return AuthUser(
            sub=str(sub),
            username=str(username) if username else None,
            email=payload.get("email"),
            roles=roles,
            groups=groups,
            raw_claims=payload,
        )

    except jwt.ExpiredSignatureError:
        logger.warning("auth: JWT validation failed — token expired%s", _req())
        return None
    except jwt.InvalidAudienceError:
        logger.warning("auth: JWT validation failed — invalid audience%s", _req())
        return None
    except jwt.InvalidIssuerError:
        logger.warning("auth: JWT validation failed — invalid issuer%s", _req())
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("auth: JWT validation failed — %s%s", exc, _req())
        return None
    except requests.RequestException as exc:
        logger.error("auth: failed to fetch JWKS — %s%s", exc, _req())
        return None
    except Exception as exc:
        # Fail closed — never leak internals
        logger.error("auth: unexpected JWT validation error — %s%s", exc, _req())
        return None
