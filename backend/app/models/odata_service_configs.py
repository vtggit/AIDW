"""OdataServiceConfig data models."""

from pydantic import BaseModel, Field


class OdataServiceConfigCreate(BaseModel):
    """Request model for creating a odata_service_config."""

    name: str = Field(..., min_length=1)
    metadata_path: str | None = Field(default=None)
    default_entity_set: str | None = Field(default=None)


class OdataServiceConfigUpdate(BaseModel):
    """Request model for updating a odata_service_config (all fields optional)."""

    name: str | None = Field(default=None)
    metadata_path: str | None = Field(default=None)
    default_entity_set: str | None = Field(default=None)


class OdataServiceConfigResponse(BaseModel):
    """Response model for a odata_service_config record."""

    id: str
    name: str
    metadata_path: str | None = None
    default_entity_set: str | None = None
    created_at: str
    updated_at: str
