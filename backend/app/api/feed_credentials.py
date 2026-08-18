"""FeedCredential API routes."""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.authorization import ROLE_ADMIN, require_role
from app.auth.dependencies import require_authenticated_user
from app.auth.models import AuthUser
from app.models.feed_credentials import (
    FeedCredentialCreate,
    FeedCredentialResponse,
    FeedCredentialUpdate,
)
from app.repositories.feed_credentials_postgres_repository import (
    FeedCredentialPostgresRepository,
)
from app.services.feed_credentials_service import FeedCredentialService

router = APIRouter(prefix="/api/feed-credentials", tags=["feed-credentials"])

_repository = FeedCredentialPostgresRepository()
_service = FeedCredentialService(repository=_repository)


def get_service() -> FeedCredentialService:
    return _service


@router.get("", response_model=list[FeedCredentialResponse])
def list_feed_credentials(
    _user: AuthUser = Depends(require_authenticated_user),
    service: FeedCredentialService = Depends(get_service),
):
    return service.list_feed_credentials()


@router.post(
    "", response_model=FeedCredentialResponse, status_code=status.HTTP_201_CREATED
)
def create_feed_credential(
    payload: FeedCredentialCreate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FeedCredentialService = Depends(get_service),
):
    return service.create_feed_credential(payload)


@router.post("/{entity_id}/rotate")
def rotate_feed_credential(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FeedCredentialService = Depends(get_service),
):
    """Rotate a feed credential's key.

    Generates a fresh key, persists only its SHA-256 digest and 8-char prefix,
    and returns the updated record plus the plaintext key exactly once. The
    plaintext is never persisted and never logged.
    """
    existing = service.get_feed_credential(entity_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FeedCredential '{entity_id}' not found.",
        )

    plaintext_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    key_prefix = plaintext_key[:8]

    updated = service.update_feed_credential(
        entity_id,
        FeedCredentialUpdate(key_hash=key_hash, key_prefix=key_prefix),
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FeedCredential '{entity_id}' not found.",
        )

    result = dict(updated)
    result["key"] = plaintext_key
    return result


@router.get("/{entity_id}", response_model=FeedCredentialResponse)
def get_feed_credential(
    entity_id: str,
    _user: AuthUser = Depends(require_authenticated_user),
    service: FeedCredentialService = Depends(get_service),
):
    entity = service.get_feed_credential(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FeedCredential '{entity_id}' not found.",
        )
    return entity


@router.put("/{entity_id}", response_model=FeedCredentialResponse)
def update_feed_credential(
    entity_id: str,
    payload: FeedCredentialUpdate,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FeedCredentialService = Depends(get_service),
):
    entity = service.update_feed_credential(entity_id, payload)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FeedCredential '{entity_id}' not found.",
        )
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feed_credential(
    entity_id: str,
    _user: AuthUser = Depends(require_role(ROLE_ADMIN)),
    service: FeedCredentialService = Depends(get_service),
):
    if not service.delete_feed_credential(entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FeedCredential '{entity_id}' not found.",
        )
