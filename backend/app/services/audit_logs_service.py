"""Business logic for audit_logs."""

from app.models.audit_logs import AuditLogCreate, AuditLogUpdate
from app.repositories.audit_logs_postgres_repository import AuditLogPostgresRepository


class AuditLogService:
    """Service layer for audit_logs."""

    def __init__(self, repository: AuditLogPostgresRepository):
        self.repository = repository

    def list_audit_logs(self) -> list[dict]:
        return self.repository.list_all()

    def get_audit_log(self, entity_id: str) -> dict | None:
        return self.repository.get_by_id(entity_id)

    def create_audit_log(self, payload: AuditLogCreate) -> dict:
        return self.repository.create(payload.model_dump())

    def update_audit_log(self, entity_id: str, payload: AuditLogUpdate) -> dict | None:
        return self.repository.update(entity_id, payload.model_dump(exclude_unset=True))

    def delete_audit_log(self, entity_id: str) -> bool:
        return self.repository.delete(entity_id)
