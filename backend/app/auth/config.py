# AICRM authentication configuration
#
# All values are environment-driven so no tenant-specific secrets are
# hardcoded.  In development the defaults provide a working stub that
# can be replaced with real IdP metadata later.

import os

# ---------------------------------------------------------------------------
# Feature flag — set to "false" to temporarily bypass auth (e.g. for CI).
# ---------------------------------------------------------------------------
AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "true").lower() not in (
    "false",
    "0",
    "off",
)

# ---------------------------------------------------------------------------
# Identity Provider (IdP) metadata
#
# For enterprise deployment these point to your Keycloak / Entra ID / Auth0
# issuer.  The defaults are development placeholders.
# ---------------------------------------------------------------------------
AUTH_ISSUER: str = os.getenv(
    "AUTH_ISSUER",
    "https://dev.example.com/realms/aicrm",
)
AUTH_CLIENT_ID: str = os.getenv("AUTH_CLIENT_ID", "aicrm-backend")
AUTH_AUDIENCE: str = os.getenv("AUTH_AUDIENCE", AUTH_CLIENT_ID)
AUTH_JWKS_URL: str = os.getenv(
    "AUTH_JWKS_URL",
    f"{AUTH_ISSUER}/protocol/openid-connect/certs",
)

# Supported signing algorithms (comma-separated env var, default RS256).
# Common enterprise values: RS256, RS384, RS512, ES256, ES384, PS256.
_AUTH_ALGORITHMS_RAW: str = os.getenv("AUTH_ALGORITHMS", "RS256")
AUTH_ALGORITHMS: list[str] = [
    a.strip() for a in _AUTH_ALGORITHMS_RAW.split(",") if a.strip()
]

# For backward compatibility — single-algorithm env var still works.
AUTH_ALGORITHM: str = AUTH_ALGORITHMS[0] if AUTH_ALGORITHMS else "RS256"

# ---------------------------------------------------------------------------
# JWKS caching
#
# Controls how long the fetched JWKS key set is cached before the next
# refresh.  Prevents hammering the IdP on every request.
# ---------------------------------------------------------------------------
AUTH_JWKS_CACHE_TTL: int = int(os.getenv("AUTH_JWKS_CACHE_TTL", "3600"))

# ---------------------------------------------------------------------------
# Role / Group claim names
#
# Different IdPs place roles and groups in different JWT claim locations.
# These settings let you normalise them without code changes.
#
# AUTH_ROLE_CLAIMS — comma-separated list of claim paths to scan for roles.
#   Supports dot-notation for nested claims (e.g. "realm_access.roles").
#   Default covers Keycloak and generic conventions.
#
# AUTH_GROUP_CLAIMS — comma-separated list of claim paths to scan for groups.
# ---------------------------------------------------------------------------
_AUTH_ROLE_CLAIMS_RAW: str = os.getenv(
    "AUTH_ROLE_CLAIMS",
    "roles,realm_access.roles,resource_access.{client_id}.roles",
)
AUTH_ROLE_CLAIMS: list[str] = [
    c.strip() for c in _AUTH_ROLE_CLAIMS_RAW.split(",") if c.strip()
]

_AUTH_GROUP_CLAIMS_RAW: str = os.getenv(
    "AUTH_GROUP_CLAIMS",
    "groups",
)
AUTH_GROUP_CLAIMS: list[str] = [
    c.strip() for c in _AUTH_GROUP_CLAIMS_RAW.split(",") if c.strip()
]

# ---------------------------------------------------------------------------
# Development-mode token stub
#
# When AUTH_MODE=development the backend accepts a simple bearer token
# whose value matches AUTH_DEV_TOKEN.  This is ONLY for local development
# and MUST be replaced with real JWT validation before any deployment.
# ---------------------------------------------------------------------------
AUTH_MODE: str = os.getenv("AUTH_MODE", "development")  # "development" | "production"
AUTH_DEV_TOKEN: str = os.getenv("AUTH_DEV_TOKEN", "dev-secret-token")

# Comma-separated roles assigned to the dev token (default: "user").
# Set AUTH_DEV_ROLES="admin,user" to make the dev token act as an admin.
_AUTH_DEV_ROLES_RAW: str = os.getenv("AUTH_DEV_ROLES", "user")
AUTH_DEV_ROLES: list[str] = [
    r.strip() for r in _AUTH_DEV_ROLES_RAW.split(",") if r.strip()
]
