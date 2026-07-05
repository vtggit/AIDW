"""Container hardening (#122) — non-root users, pinned digests, locked-down compose."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _service_block(compose: str, name: str) -> str:
    m = re.search(r"(?ms)^  " + name + r":\n(.*?)(?=^  \w|^volumes:|\Z)", compose)
    assert m, name + " service missing from docker-compose.yml"
    return m.group(1)


def test_container_hardening():
    backend = (ROOT / "backend" / "Dockerfile").read_text()
    frontend = (ROOT / "app" / "Dockerfile").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    for name, df in (("backend", backend), ("frontend", frontend)):
        froms = re.findall(r"(?m)^FROM\s+(\S+)", df)
        assert froms, name
        for image in froms:
            assert "@sha256:" in image, name + ": unpinned base image " + image
        users = [m.start() for m in re.finditer(r"(?m)^USER\s+(?!root)\S+", df)]
        assert users, name + ": no non-root USER directive"
        run_pts = [m.start() for m in re.finditer(r"(?m)^(?:ENTRYPOINT|CMD)\b", df)]
        if run_pts:
            assert users[0] < min(run_pts), name + ": USER must precede CMD/ENTRYPOINT"
    for svc in ("backend", "frontend"):
        block = _service_block(compose, svc)
        assert "read_only: true" in block, svc
        assert re.search(r"cap_drop:\s*\n\s*- ALL", block), svc
        assert "tmpfs:" in block and "- /tmp" in block, svc
    for svc in ("db", "test-db"):
        block = _service_block(compose, svc)
        assert "read_only" not in block, svc + ": postgres must stay writable"
