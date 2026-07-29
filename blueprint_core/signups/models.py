from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class AlphaSignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Person's name")
    email: str = Field(..., min_length=3, max_length=254, description="Contact email")
    organization: str | None = Field(None, max_length=160, description="Organization or team")
    additional_info: str | None = Field(None, max_length=1200, description="Optional launch or use-case context")

    @field_validator("name", "email", mode="before")
    @classmethod
    def strip_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("organization", "additional_info", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str | None) -> str:
        if not value:
            raise ValueError("Name is required.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str:
        if not value:
            raise ValueError("Email is required.")
        normalized = value.lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class AlphaSignupResponse(BaseModel):
    ok: bool
    message: str
