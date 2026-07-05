# AICRM backend configuration
#
# All runtime values are driven by environment variables with explicit,
# safe defaults.  There are no hidden fallback paths — if an env var is
# not set, the default below is used.  This makes local, container, and
# hosted deployments follow the same mental model.

import os

# ---------------------------------------------------------------------------
# Application identity
# ---------------------------------------------------------------------------
APP_NAME: str = "AIDW"


# Read APP_VERSION from environment first (container deployments),
# then from the canonical VERSION file at repo root, then fall back
# to a hardcoded default.  The VERSION file is the source of truth.
def _get_app_version() -> str:
    env_version = os.getenv("APP_VERSION")
    if env_version:
        return env_version
    # Try to read VERSION from repo root (one level above backend/)
    version_file = os.path.join(os.path.dirname(__file__), "..", "..", "VERSION")
    try:
        with open(version_file) as f:
            return f.read().strip()
    except OSError:
        pass
    return "0.1.0"


APP_VERSION: str = _get_app_version()

# Build / traceability metadata
# These are injected at build time via environment variables (e.g. in CI or
# Docker build --build-arg).  They are never hardcoded in source.
GIT_SHA: str = os.getenv("GIT_SHA", "")
BUILD_TIMESTAMP: str = os.getenv("BUILD_TIMESTAMP", "")

ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# CORS — comma-separated list of allowed frontend origins
# ---------------------------------------------------------------------------
_CORS_RAW: str = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080",
)
CORS_ORIGINS: list[str] = [o.strip() for o in _CORS_RAW.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# PostgreSQL configuration
# All values can be overridden via environment variables.
# ---------------------------------------------------------------------------
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_NAME: str = os.getenv("DB_NAME", "aicrm")
DB_USER: str = os.getenv("DB_USER", "aicrm")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "aicrm")
