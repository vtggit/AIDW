"""Proving test for issue #639: Alembic env.py must use psycopg2 driver explicitly."""

from pathlib import Path


def test_issue639_surgical() -> None:
    """The Alembic connection URL must name the psycopg2 driver explicitly."""
    env_path = Path(__file__).resolve().parent.parent / "migrations" / "env.py"
    content = env_path.read_text(encoding="utf-8")
    assert (
        "postgresql+psycopg2://" in content
    ), "env.py must use 'postgresql+psycopg2://' driver prefix"
    assert (
        "postgresql://" not in content
    ), "env.py must not use bare 'postgresql://' without explicit driver"
