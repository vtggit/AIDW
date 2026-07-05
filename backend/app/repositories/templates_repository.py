"""In-memory repository for Templates."""

from datetime import datetime


class TemplateRepository:
    """Simple in-memory repository for template CRUD operations."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def list_all(self) -> list[dict]:
        return list(self._store.values())

    def get_by_id(self, template_id: str) -> dict | None:
        return self._store.get(template_id)

    def create(self, data: dict) -> dict:
        template_id = data.get("id", _generate_id())
        now = datetime.utcnow().isoformat()
        record = {
            "id": template_id,
            "name": data["name"],
            "category": data.get("category", "other"),
            "subject": data.get("subject"),
            "content": data.get("content", ""),
            "created_at": now,
            "updated_at": now,
        }
        self._store[template_id] = record
        return record

    def update(self, template_id: str, data: dict) -> dict | None:
        record = self._store.get(template_id)
        if not record:
            return None

        for key in ("name", "category", "subject", "content"):
            if key in data:
                record[key] = data[key]

        record["updated_at"] = datetime.utcnow().isoformat()
        self._store[template_id] = record
        return record

    def delete(self, template_id: str) -> bool:
        return self._store.pop(template_id, None) is not None


def _generate_id() -> str:
    """Generate a simple unique ID."""
    import random
    import time

    return f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
