"""opentelemetry-api is pinned to exactly 1.45.2 in backend/constraints.txt."""

from pathlib import Path

BACKEND = Path(__file__).parents[1]


def test_issue841_freeform():
    lines = [
        line.strip()
        for line in (BACKEND / "constraints.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    otel_lines = [line for line in lines if line.startswith("opentelemetry-api==")]
    assert otel_lines == ["opentelemetry-api==1.45.2"]
    assert "opentelemetry-api==1.45.1" not in lines
