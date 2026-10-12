"""Every package the backend installs has an exact pinned version.

On 2026-10-12 a rebuilt backend image picked up a new release of an unpinned
dependency and could not start, while CI stayed green because the CI machine still
had an older copy installed. The image and CI now install with
``-c constraints.txt``: the same exact versions everywhere, changed only on purpose
with ``scripts/refresh_constraints.sh``.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _required_names() -> list[str]:
    names = []
    for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0]
        names.append(_normalise(name))
    return names


def _pins() -> dict[str, str]:
    pins = {}
    for line in (BACKEND / "constraints.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, f"constraints.txt must pin exactly, got: {line}"
        name, version = line.split("==", 1)
        pins[_normalise(name)] = version
    return pins


def test_every_requirement_has_an_exact_pin():
    pins = _pins()
    missing = [name for name in _required_names() if name not in pins]
    assert missing == [], (
        "no pinned version in backend/constraints.txt for: "
        + ", ".join(missing)
        + ". Run scripts/refresh_constraints.sh and commit the result."
    )
    assert len(pins) >= len(set(_required_names()))


def test_the_image_installs_with_the_constraints():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    installs = [ln for ln in dockerfile.splitlines() if "pip install" in ln]
    assert installs, "the Dockerfile no longer installs with pip"
    for line in installs:
        assert "-c constraints.txt" in line, line
    assert re.search(r"^COPY .*constraints\.txt", dockerfile, re.M)


def test_ci_installs_with_the_constraints():
    workflows = sorted((REPO / ".github" / "workflows").glob("*.yml"))
    assert workflows
    for workflow in workflows:
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "pip install" in line and "requirements.txt" in line:
                assert (
                    "-c backend/constraints.txt" in line
                ), f"{workflow.name}: {line.strip()}"
