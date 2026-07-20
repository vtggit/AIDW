"""SequenceFlow data models."""

from pydantic import BaseModel, Field


class SequenceFlowCreate(BaseModel):
    """Request model for creating a sequence_flow."""

    process_definition_id: str | None = Field(default=None)

    name: str = Field(..., min_length=1)
    flow_key: str | None = Field(default=None)
    source_step: str | None = Field(default=None)
    target_step: str | None = Field(default=None)
    condition_expression: str | None = Field(default=None)
    is_default: bool | None = Field(default=None)


class SequenceFlowUpdate(BaseModel):
    """Request model for updating a sequence_flow (all fields optional)."""

    process_definition_id: str | None = Field(default=None)

    name: str | None = Field(default=None)
    flow_key: str | None = Field(default=None)
    source_step: str | None = Field(default=None)
    target_step: str | None = Field(default=None)
    condition_expression: str | None = Field(default=None)
    is_default: bool | None = Field(default=None)


class SequenceFlowResponse(BaseModel):
    """Response model for a sequence_flow record."""

    process_definition_id: str | None = None

    id: str
    name: str
    flow_key: str | None = None
    source_step: str | None = None
    target_step: str | None = None
    condition_expression: str | None = None
    is_default: bool | None = None
    created_at: str
    updated_at: str
