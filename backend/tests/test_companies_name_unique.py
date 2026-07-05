"""Unique-constraint test — uq_companies_name enforced; duplicates return 409."""

import psycopg2


def test_companies_name_unique(client, admin_headers):
    from app.db.connection import get_connection_params

    conn = psycopg2.connect(**get_connection_params())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = %s AND indexname = %s",
                ("companies", "uq_companies_name"),
            )
            rows = cur.fetchall()
            assert len(rows) == 1 and "UNIQUE" in rows[0][0].upper()
            assert "LOWER" in rows[0][0].upper()  # case-insensitive expression
    finally:
        conn.close()
    first = client.post(
        "/api/companies", json={"name": "Unique Target"}, headers=admin_headers
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        "/api/companies", json={"name": "Unique Target"}, headers=admin_headers
    )
    assert dup.status_code == 409, dup.text
    assert "name" in dup.text or "Duplicate" in dup.text
    casev = client.post(
        "/api/companies", json={"name": "UNIQUE TARGET"}, headers=admin_headers
    )
    assert casev.status_code == 409, casev.text  # case-variant duplicate rejected
    other = client.post(
        "/api/companies", json={"name": "Another Target"}, headers=admin_headers
    )
    assert other.status_code == 201, other.text  # distinct values fine; pool survives
    rename = client.put(
        "/api/companies/" + other.json()["id"],
        json={"name": "Unique Target"},
        headers=admin_headers,
    )
    assert rename.status_code == 409, rename.text  # renaming onto a duplicate rejected
