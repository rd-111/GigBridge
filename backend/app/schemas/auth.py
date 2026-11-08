"""Authentication request and response schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, password: str) -> str:
        if (
            not any(char.islower() for char in password)
            or not any(char.isupper() for char in password)
            or not any(char.isdigit() for char in password)
            or not any(not char.isalnum() for char in password)
        ):
            raise ValueError(
                "Password must contain uppercase and lowercase letters, a number, and a symbol."
            )
        return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class WorkspaceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    currency: str
    timezone: str
    role: str


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool


class RegistrationResponse(BaseModel):
    user: UserResponse
    workspace: WorkspaceSummary


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(UserResponse):
    workspaces: list[WorkspaceSummary]
