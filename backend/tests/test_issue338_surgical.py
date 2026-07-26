"""Proving test for issue #338: grid span fields in item-data response."""

from unittest.mock import MagicMock, patch

from app.dashboard.data_service import item_data


def test_issue338_surgical():
    """Assert grid_col_span and grid_row_span are surfaced on the sampled path."""
    item = {
        "id": "i1",
        "title": "T",
        "item_type": "kpi",
        "aggregation": "count",
        "grid_col_span": 4,
        "grid_row_span": 2,
    }
    fields = [{"field_role": "measure", "id": "f1", "name": "val", "dataset_id": "d1"}]
    ds = {"id": "d1", "name": "ds1", "source_id": "s1"}
    conn = {"endpoint": "http://x.com/api"}

    cur = MagicMock()
    # Call order: fetchone(item), fetchall(fields), fetchone(ds), fetchone(conn),
    # fetchall(flagged), fetchall(key_fields), fetchall(suppressed)
    cur.fetchone.side_effect = [item, ds, conn]
    cur.fetchall.side_effect = [fields, [], [], []]

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = cur
    mock_ctx.__exit__.return_value = False

    with (
        patch("app.dashboard.data_service.get_cursor", return_value=mock_ctx),
        patch("app.dashboard.data_service._fetch_rows", return_value=b"{}"),
        patch("app.dashboard.data_service.parse_rows", return_value=[{"val": "1"}]),
    ):
        result = item_data("i1")

    assert result["grid_col_span"] == 4
    assert result["grid_row_span"] == 2
