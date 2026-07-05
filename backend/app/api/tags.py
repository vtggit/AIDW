"""Contact Tags API routes — CRUD for tag definitions and contact-tag assignments."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.models import AuthUser
from app.models.contact_tags import ContactTagsUpdate, TagCreate, TagResponse, TagUpdate
from app.repositories.tags_postgres_repository import TagsPostgresRepository

router = APIRouter(prefix="/api/tags", tags=["tags"])
_repository = TagsPostgresRepository()


@router.get("", response_model=list[TagResponse])
def list_tags(
    response: Response,
    limit: int = Query(20, ge=0, le=100),
    offset: int = Query(0, ge=0),
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """List all available tags."""
    rows = _repository.list_all()
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset : offset + limit]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Create a new tag. Duplicate names (case-insensitive) return existing tag."""
    try:
        return _repository.create(payload.trimmed_name, payload.color)
    except Exception as exc:
        if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tag '{payload.trimmed_name}' already exists.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )


@router.put("/{tag_id}", response_model=TagResponse)
def update_tag(
    tag_id: str,
    payload: TagUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Update an existing tag."""
    data = payload.model_dump(exclude_none=True)
    if not data:
        existing = _repository.get_by_id(tag_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
        return existing
    try:
        result = _repository.update(tag_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
    return result


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Delete a tag (also removes all mappings)."""
    deleted = _repository.delete(tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")
    return None


# ---- Contact-tag assignment endpoint (also accessible via /api/contacts) ----


@router.put("/contacts/{contact_id}/tags", status_code=status.HTTP_204_NO_CONTENT)
def set_contact_tags(
    contact_id: str,
    payload: ContactTagsUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
):
    """Replace all tags for a contact with the provided list of tag IDs."""
    _repository.set_tags_for_contact(contact_id, payload.tag_ids)
    return None
