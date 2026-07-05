"""Company data models."""

from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    """Request model for creating a company."""

    name: str = Field(..., min_length=1)
    website: str | None = Field(default=None)
    industry: str | None = Field(default=None)
    employee_count: int | None = Field(default=None)


class CompanyUpdate(BaseModel):
    """Request model for updating a company (all fields optional)."""

    name: str | None = Field(default=None)
    website: str | None = Field(default=None)
    industry: str | None = Field(default=None)
    employee_count: int | None = Field(default=None)


class CompanyResponse(BaseModel):
    """Response model for a company record."""

    id: str
    name: str
    website: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    created_at: str
    updated_at: str
