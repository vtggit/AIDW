"""PostgreSQL repository for dashboard_item_layouts."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row_record) -> dict:
    record_dict = dict(row_record)
    for key in ("created_at", "updated_at"):
        if record_dict.get(key) and isinstance(record_dict[key], datetime):
            record_dict[key] = record_dict[key].isoformat()
    return record_dict


class DashboardItemLayoutPostgresRepository:
    """PostgreSQL repository for the dashboard_item_layouts table.

    All write operations are scoped to a specific user_id so that callers
    can only manage their own rows.  Read operations also filter by owner.
    """

    def list_by_user(self, caller_user_id: str) -> list[dict]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_item_layouts WHERE user_id = %s ORDER BY created_at DESC",
                (caller_user_id,),
            )
            return [_row_to_dict(row_record) for row_record in cur.fetchall()]

    def get_by_id_and_owner(self, entity_id: str, owner_user_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM dashboard_item_layouts WHERE id = %s AND user_id = %s",
                (entity_id, owner_user_id),
            )
            row_record = cur.fetchone()
            return _row_to_dict(row_record) if row_record else None

    def create_for_user(self, data: dict, owner_user_id: str) -> dict:
        new_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO dashboard_item_layouts (id, name, user_id, dashboard_item_id, grid_col_span, grid_col_start, grid_row_span, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    new_id,
                    data.get("name"),
                    owner_user_id,
                    data.get("dashboard_item_id"),
                    data.get("grid_col_span"),
                    data.get("grid_col_start"),
                    data.get("grid_row_span"),
                    now,
                    now,
                ),
            )
        return self.get_by_id_and_owner(new_id, owner_user_id)

    def update_for_owner(
        self, entity_id: str, data: dict, owner_user_id: str
    ) -> dict | None:
        existing_record = self.get_by_id_and_owner(entity_id, owner_user_id)
        if existing_record is None:
            return None

        updatable_fields = (
            "name",
            "dashboard_item_id",
            "grid_col_span",
            "grid_col_start",
            "grid_row_span",
        )
        fields_to_update = [
            field_name for field_name in updatable_fields if field_name in data
        ]
        if not fields_to_update:
            return existing_record

        set_clauses = [f"{field_name} = %s" for field_name in fields_to_update]
        set_clauses.append("updated_at = %s")
        values_list = [data[field_name] for field_name in fields_to_update]
        values_list.append(datetime.now(timezone.utc))

        with get_cursor() as cur:
            cur.execute(
                f"UPDATE dashboard_item_layouts SET {', '.join(set_clauses)} WHERE id = %s AND user_id = %s",
                values_list + [entity_id, owner_user_id],
            )
        return self.get_by_id_and_owner(entity_id, owner_user_id)

    def delete_for_owner(self, entity_id: str, owner_user_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute(
                "DELETE FROM dashboard_item_layouts WHERE id = %s AND user_id = %s",
                (entity_id, owner_user_id),
            )
            return cur.rowcount > 0
