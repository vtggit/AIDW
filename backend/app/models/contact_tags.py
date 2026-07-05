"""Contact tag data models."""

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """Request model for creating a tag."""

    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#3b82f6", max_length=20)

    @property
    def trimmed_name(self) -> str:
        return self.name.strip()


class TagUpdate(BaseModel):
    """Request model for updating a tag."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=20)


class TagResponse(BaseModel):
    """Response model for a tag."""

    id: str
    name: str
    color: str
    created_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "tag-abc-123",
                "name": "Customer",
                "color": "#ef4444",
                "created_at": "2025-01-01T00:00:00",
            }
        }


class ContactTagsUpdate(BaseModel):
    """Request to set the full list of tag IDs for a contact."""

    tag_ids: list[str] = Field(default_factory=list)
