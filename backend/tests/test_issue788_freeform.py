"""Proving test for issue #788: docker-compose mounts the repo VERSION file at
/VERSION for the backend service (read-only), and app.config reports that file's
content when APP_VERSION is unset."""

import os
from pathlib import Path


def _backend_service_lines(compose_text: str) -> list[str]:
    """Return the raw lines of the `backend` service block under `services:`.

    Minimal indentation-based scan (no YAML library): the backend block starts
    at the 2-space-indented `backend:` key and ends at the next 2-space key
    (or a top-level key).
    """
    in_services = False
    in_backend = False
    backend_lines: list[str] = []
    for line in compose_text.splitlines():
        if not in_services:
            if line.rstrip() == "services:":
                in_services = True
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            if in_backend:
                backend_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break
        if indent == 2:
            if in_backend:
                break
            in_backend = line.rstrip() == "  backend:"
            continue
        if in_backend:
            backend_lines.append(line)
    assert in_backend, "backend service block not found in docker-compose.yml"
    return backend_lines


def _volumes_entries(backend_lines: list[str]) -> list[str]:
    """Return the list entries under the service-level `volumes:` key."""
    entries: list[str] = []
    in_volumes = False
    for line in backend_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= 4:
            in_volumes = indent == 4 and stripped == "volumes:"
            continue
        if in_volumes and stripped.startswith("- "):
            entries.append(stripped[2:].strip())
    return entries


def test_issue788_freeform(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    version_text = (repo_root / "VERSION").read_text(encoding="utf-8")

    # The backend service mounts ./VERSION read-only at /VERSION
    entries = _volumes_entries(_backend_service_lines(compose_text))
    assert (
        "./VERSION:/VERSION:ro" in entries
    ), f"backend service must mount ./VERSION:/VERSION:ro under volumes, got {entries!r}"

    # The mount point is exactly where app/config.py looks when running from /app/app/config.py
    assert (
        os.path.normpath(os.path.join("/app/app", "..", "..", "VERSION")) == "/VERSION"
    )

    # With APP_VERSION unset, _get_app_version() reports the repo VERSION file
    monkeypatch.delenv("APP_VERSION", raising=False)
    from app import config

    assert config._get_app_version() == version_text.strip()
