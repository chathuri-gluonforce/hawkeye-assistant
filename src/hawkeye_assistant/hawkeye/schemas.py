"""Pydantic models for the Hawkeye integration."""

from datetime import date, datetime
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    computed_field,
    field_validator,
    model_validator,
)


class LoginRequest(BaseModel):
    organization_id: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)  # hidden in repr/logs


class User(BaseModel):
    """The part of Hawkeye's user profile that the assistant needs."""

    model_config = ConfigDict(extra="ignore")

    id: str
    organization_id: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool = True


class SessionInfo(BaseModel):
    """What the browser may see about its session. Never contains Hawkeye tokens."""

    user: User
    csrf_token: str
    expires_at: datetime


# --- Audit logs (read-only) ---
class AuditFilters(BaseModel):
    """Everything a caller (including the LLM) may ask of the audit log.

    Values are checked here, so nothing odd can reach Hawkeye. Unknown fields
    (such as a URL) are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=1000)
    page_size: int = Field(default=20, ge=1, le=100)
    actor_user_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{1,64}$")
    action: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{1,64}$")  # MATCH_APPROVED
    category: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    date_from: date | None = None
    date_to: date | None = None
    automated_only: bool | None = None

    @field_validator("action", mode="before")
    @classmethod
    def upper_action(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    organization_id: str
    entity_type: str
    entity_id: str | None = None
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    actor_user_id: str | None = None
    actor_role: str | None = None
    actor_full_name: str | None = None
    actor_email: str | None = None
    created_at: datetime  # UTC, no timezone marker

    @field_validator("details", mode="before")
    @classmethod
    def details_default(cls, value: object) -> object:
        return {} if value is None else value

    @computed_field
    @property
    def automated(self) -> bool:
        """Hawkeye records automated events with no human actor."""
        return self.actor_user_id is None


class AuditPage(BaseModel):
    items: list[AuditRecord]
    page: int
    page_size: int
    total: int

    @computed_field
    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total