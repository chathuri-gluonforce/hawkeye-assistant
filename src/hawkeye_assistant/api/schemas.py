"""Request and response models for the assistant's HTTP API."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from hawkeye_assistant.hawkeye.schemas import AuditFilters, SessionInfo


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    use_memory: bool = True
    use_best_prompt: bool = True
    filters: AuditFilters | None = None


class IntentChatResponse(BaseModel):
    kind: Literal["intent"] = "intent"
    text: str
    intent: str
    prompt: str
    lessons: list[dict[str, Any]]


class AuditRecordSummaryResponse(BaseModel):
    id: str
    action: str
    entity_type: str
    entity_id: str | None
    actor_name: str | None
    actor_email: str | None
    actor_role: str | None
    created_at: datetime
    automated: bool
    details: dict[str, Any]


class AuditAnswerResponse(BaseModel):
    answer: str
    filters: AuditFilters
    records: list[AuditRecordSummaryResponse]
    page: int
    page_size: int
    total: int
    has_more: bool


class AuditChatResponse(BaseModel):
    kind: Literal["audit_results"] = "audit_results"
    intent: Literal["audit_query"] = "audit_query"
    result: AuditAnswerResponse


ChatResponse = Annotated[
    IntentChatResponse | AuditChatResponse, Field(discriminator="kind")
]


class LoginResponse(SessionInfo):
    """Public assistant session details; never contains Hawkeye cookies."""
