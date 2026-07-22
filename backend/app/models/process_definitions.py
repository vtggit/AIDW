"""ProcessDefinition data models."""

from pydantic import BaseModel, Field


class ProcessDefinitionCreate(BaseModel):
    """Request model for creating a process_definition."""

    review_cycle_days: int | None = Field(default=None)

    name: str = Field(..., min_length=1)
    process_key: str | None = Field(default=None)
    version: str | None = Field(default=None)
    description: str | None = Field(default=None)
    status: str | None = Field(default=None)


class ProcessDefinitionUpdate(BaseModel):
    """Request model for updating a process_definition (all fields optional)."""

    review_cycle_days: int | None = Field(default=None)

    name: str | None = Field(default=None)
    process_key: str | None = Field(default=None)
    version: str | None = Field(default=None)
    description: str | None = Field(default=None)
    status: str | None = Field(default=None)


class ProcessDefinitionResponse(BaseModel):
    """Response model for a process_definition record."""

    review_cycle_days: int | None = None

    id: str
    name: str
    process_key: str | None = None
    version: str | None = None
    description: str | None = None
    status: str | None = None
    created_at: str
    updated_at: str
