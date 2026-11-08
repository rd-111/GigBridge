"""Workspace request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkspaceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "WorkspaceUpdateRequest":
        """Omitted fields are allowed, but setting a required field to null is not."""

        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Workspace settings cannot be null.")
        return self


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner_id: UUID
    currency: str
    timezone: str
    created_at: datetime
    updated_at: datetime
