"""Proof for issue #459 — OData naming helpers in app.feed.naming.

Pure pytest: no database rows, no HTTP. Imports the three helpers from
``app.feed.naming`` and asserts concrete values for each.
"""

from app.feed.naming import edm_type_for, entity_set_names, odata_identifier


def test_issue459_freeform():
    # --- odata_identifier -------------------------------------------------
    assert odata_identifier("Order Items") == "Order_Items"
    assert odata_identifier("2024 sales") == "_2024_sales"
    assert odata_identifier("") == "_"
    long_name = "a" * 200
    assert len(odata_identifier(long_name)) == 128
    assert odata_identifier("Orders") == "Orders"

    # --- entity_set_names -------------------------------------------------
    # Two datasets both named "Orders": the LATER created_at is supplied
    # first in the input, but the earlier-created id must keep the bare
    # name and the later one gets the _2 suffix (collision resolved by
    # created_at, not input position). A third dataset "Customers" maps to
    # "Customers" and there are no other entries.
    earlier = {
        "id": "ds-earlier",
        "name": "Orders",
        "created_at": "2024-01-01T00:00:00Z",
    }
    later = {"id": "ds-later", "name": "Orders", "created_at": "2024-06-01T00:00:00Z"}
    customers = {
        "id": "ds-customers",
        "name": "Customers",
        "created_at": "2024-03-01T00:00:00Z",
    }

    mapping = entity_set_names([later, earlier, customers])

    assert mapping == {
        "Orders": "ds-earlier",
        "Orders_2": "ds-later",
        "Customers": "ds-customers",
    }
    assert len(mapping) == 3

    # --- edm_type_for -----------------------------------------------------
    assert edm_type_for("Edm.Int32") == "Edm.Int32"
    assert edm_type_for("edm.datetimeoffset") == "Edm.DateTimeOffset"
    assert edm_type_for("Edm.DateTime") == "Edm.DateTimeOffset"
    assert edm_type_for("Edm.Time") == "Edm.TimeOfDay"
    assert edm_type_for("Edm.Float") == "Edm.Single"
    assert edm_type_for("float") == "Edm.Double"
    assert edm_type_for("integer") == "Edm.Int32"
    assert edm_type_for("timestamp with time zone") == "Edm.DateTimeOffset"
    assert edm_type_for("datetime2") == "Edm.DateTimeOffset"
    assert edm_type_for("date") == "Edm.Date"
    assert edm_type_for("uuid") == "Edm.Guid"
    assert edm_type_for(None) == "Edm.String"
    assert edm_type_for("") == "Edm.String"
    assert edm_type_for("varchar") == "Edm.String"
