"""In-memory repository for Contacts."""

from datetime import datetime


class ContactRepository:
    """Simple in-memory repository for contact CRUD operations."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def list_all(self) -> list[dict]:
        return list(self._store.values())

    def get_by_id(self, contact_id: str) -> dict | None:
        return self._store.get(contact_id)

    def create(self, data: dict) -> dict:
        contact_id = data.get("id", _generate_id())
        now = datetime.utcnow().isoformat()
        record = {
            "id": contact_id,
            "name": data["name"],
            "email": data.get("email"),
            "phone": data.get("phone"),
            "company": data.get("company"),
            "status": data.get("status", "active"),
            "notes": data.get("notes"),
            "created_at": now,
            "updated_at": now,
        }
        self._store[contact_id] = record
        return record

    def update(self, contact_id: str, data: dict) -> dict | None:
        record = self._store.get(contact_id)
        if not record:
            return None

        for key in ("name", "email", "phone", "company", "status", "notes"):
            if key in data:
                record[key] = data[key]

        record["updated_at"] = datetime.utcnow().isoformat()
        self._store[contact_id] = record
        return record

    def delete(self, contact_id: str) -> bool:
        return self._store.pop(contact_id, None) is not None


def _generate_id() -> str:
    """Generate a simple unique ID."""
    import random
    import time

    return f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
