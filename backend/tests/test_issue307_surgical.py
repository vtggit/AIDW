import time

from app.db.connection import get_cursor
from app.repositories.dashboard_items_postgres_repository import (
    DashboardItemPostgresRepository,
)


def test_issue307_surgical(clean_database):
    with get_cursor() as cur:
        cur.execute("DELETE FROM dashboard_items")

    repo = DashboardItemPostgresRepository()

    repo.create({"name": "item_pos_5", "position": 5})
    time.sleep(0.1)
    repo.create({"name": "item_pos_null"})
    time.sleep(0.1)
    repo.create({"name": "item_pos_1_old", "position": 1})
    time.sleep(0.1)
    repo.create({"name": "item_pos_1_new", "position": 1})

    results = repo.list_all()
    names = [r["name"] for r in results]

    assert names == ["item_pos_1_new", "item_pos_1_old", "item_pos_5", "item_pos_null"]
