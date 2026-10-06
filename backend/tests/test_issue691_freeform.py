"""Issue #691 — backend-only parity markers on non-browser routers.

AC-1 requires each of the thirteen listed router modules to carry exactly
one ``# parity: backend-only <reason>`` comment line, directly below its
module docstring, with the reason stated for that module.  AC-2 requires
the routers this issue does not list to carry no such line at all: every
other module in ``app/api`` (for example ``pipelines.py``, ``runs.py``,
``audit_logs.py``, ``feed_credentials.py``) must be free of the marker.
This test reads the router sources and asserts both halves of that
contract.
"""

from pathlib import Path

_API_DIR = Path(__file__).resolve().parent.parent / "app" / "api"

_PARITY_PREFIX = "# parity: backend-only "

_EXPECTED_REASONS = {
    "feed_odata.py": "consumed by Excel and BI clients over OData v4, never a browser screen",
    "ingest.py": "machine endpoint that starts pipeline runs (scheduler and automation)",
    "delta_cursors.py": "ingest internals: change-data-capture positions",
    "ingested_records.py": "ingest internals: the CDC op-log, browsed through datasets and dashboards",
    "workflows.py": "process-engine sidecar proxy, called by the engine integration",
    "source_credentials.py": "secret material, never listed in a browser",
    "discovery_runs.py": "run history of the Sources screen's Discover action",
    "connection_tests.py": "run history of the Sources screen's Test action",
    "field_profiles.py": "child records of a source, shown through the Sources screen",
    "dashboard_item_fields.py": "child records of a dashboard item, shown through the Dashboard",
    "suggestion_fields.py": "child records of a suggestion, shown through the Suggested Items section",
    "sequence_steps.py": "child records of a load sequence, shown through the Sequences section",
    "sequence_run_steps.py": "child records of a load sequence, shown through the Sequences section",
}

_AC2_EXAMPLE_ROUTERS = [
    "pipelines.py",
    "runs.py",
    "audit_logs.py",
    "feed_credentials.py",
]


def _parity_lines(filename: str) -> list[str]:
    path = _API_DIR / filename
    assert path.is_file(), f"missing router module: {path}"
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(_PARITY_PREFIX)
    ]


def test_issue691_freeform():
    """Listed routers carry exactly one parity line with the stated reason."""
    for filename, reason in _EXPECTED_REASONS.items():
        expected_line = _PARITY_PREFIX + reason
        parity_lines = _parity_lines(filename)
        assert parity_lines == [expected_line], (
            f"{filename}: expected exactly one parity line ({expected_line!r}), "
            f"got {parity_lines!r}"
        )

    unlisted_routers = [
        path.name
        for path in sorted(_API_DIR.glob("*.py"))
        if path.name != "__init__.py" and path.name not in _EXPECTED_REASONS
    ]
    for example in _AC2_EXAMPLE_ROUTERS:
        assert example in unlisted_routers, (
            f"AC-2 example router {example!r} missing from the API directory "
            f"listing {unlisted_routers!r}"
        )
    for filename in unlisted_routers:
        parity_lines = _parity_lines(filename)
        assert parity_lines == [], (
            f"{filename}: routers not listed by issue 691 must carry no "
            f"parity line, got {parity_lines!r}"
        )
