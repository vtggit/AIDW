"""In-memory repository for Activities."""

from datetime import datetime


class ActivityRepository:
    """Simple in-memory repository for activity CRUD operations."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def list_all(self) -> list[dict]:
        return list(self._store.values())

    def get_by_id(self, activity_id: str) -> dict | None:
        return self._store.get(activity_id)

    def create(self, data: dict) -> dict:
        activity_id = data.get("id", _generate_id())
        now = datetime.utcnow().isoformat()
        record = {
            "id": activity_id,
            "type": data["type"],
            "description": data["description"],
            "contact_name": data.get("contact_name"),
            "occurred_at": data.get("occurred_at", now),
            "due_date": data.get("due_date"),
            "status": data.get("status", "pending"),
            "created_at": now,
            "updated_at": now,
        }
        self._store[activity_id] = record
        return record

    def update(self, activity_id: str, data: dict) -> dict | None:
        record = self._store.get(activity_id)
        if not record:
            return None

        for key in (
            "type",
            "description",
            "contact_name",
            "occurred_at",
            "due_date",
            "status",
        ):
            if key in data:
                record[key] = data[key]

        record["updated_at"] = datetime.utcnow().isoformat()
        self._store[activity_id] = record
        return record

    def delete(self, activity_id: str) -> bool:
        return self._store.pop(activity_id, None) is not None


def _generate_id() -> str:
    """Generate a simple unique ID."""
    import random
    import time

    return f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
