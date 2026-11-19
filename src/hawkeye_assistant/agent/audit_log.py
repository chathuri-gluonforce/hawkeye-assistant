"""Answer audit questions from read-only Hawkeye records without exposing all fields."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from hawkeye_assistant.agent.audit_query import extract_audit_filters
from hawkeye_assistant.hawkeye.audit import AuditService
from hawkeye_assistant.hawkeye.schemas import AuditFilters, AuditRecord

QuestionKind = Literal["count", "actor", "time", "details", "list"]

_DETAIL_TERMS = ("amount", "currency", "match type", "reason", "status")


@dataclass(frozen=True)
class AuditEventSummary:
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


@dataclass(frozen=True)
class AuditAnswer:
    answer: str
    filters: AuditFilters
    records: list[AuditEventSummary]
    page: int
    page_size: int
    total: int
    has_more: bool


class AuditLogAgent:
    def __init__(self, audit_service: AuditService) -> None:
        self._audit_service = audit_service

    async def answer(
        self,
        query: str,
        session_id: str | None,
        filters: AuditFilters | None = None,
    ) -> AuditAnswer:
        filters = filters or extract_audit_filters(query)
        page = await self._audit_service.list_logs(session_id, filters)
        kind = _question_kind(query)
        detail_terms = _requested_detail_terms(query)
        records = [
            _summarize(record, detail_terms)
            for record in page.items
        ]
        if kind == "count":
            records = []

        return AuditAnswer(
            answer=_compose_answer(query, kind, page.total, page.items, filters),
            filters=filters,
            records=records,
            page=page.page,
            page_size=page.page_size,
            total=page.total,
            has_more=page.has_more and kind != "count",
        )


def _question_kind(query: str) -> QuestionKind:
    text = query.casefold()
    if re.search(r"\b(how many|count|number of)\b", text):
        return "count"
    if re.search(r"\b(who|which user|actor|performed by|created by)\b", text):
        return "actor"
    if re.search(r"\b(when|what time|which date|what date)\b", text):
        return "time"
    if re.search(r"\b(amount|currency|match type|reason|status)\b", text):
        return "details"
    return "list"


def _requested_detail_terms(query: str) -> tuple[str, ...]:
    text = query.casefold()
    return tuple(term for term in _DETAIL_TERMS if term in text)


def _summarize(
    record: AuditRecord, detail_terms: tuple[str, ...]
) -> AuditEventSummary:
    details = {}
    for key, value in record.details.items():
        normalized_key = re.sub(r"[^a-z0-9]+", " ", key.casefold()).strip()
        if any(term in normalized_key for term in detail_terms):
            details[key] = value
    return AuditEventSummary(
        id=record.id,
        action=record.action,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        actor_name=record.actor_full_name,
        actor_email=record.actor_email,
        actor_role=record.actor_role,
        created_at=record.created_at,
        automated=record.automated,
        details=details,
    )


def _compose_answer(
    query: str,
    kind: QuestionKind,
    total: int,
    records: Sequence[AuditRecord],
    filters: AuditFilters,
) -> str:
    if total == 0:
        return "No audit records matched your request."

    if kind == "count":
        qualifier = "user-performed " if filters.automated_only is False else ""
        if filters.automated_only is True:
            qualifier = "automated "
        return f"Found {total} {qualifier}audit record(s)."

    if kind == "actor":
        actors = list(
            dict.fromkeys(
                record.actor_full_name or record.actor_email or record.actor_user_id
                for record in records
                if record.actor_user_id
            )
        )
        if not actors:
            return "The matching records have no human actor recorded."
        actor_list = ", ".join(actors)
        if total > len(records):
            return f"Among the returned records, recorded actor(s): {actor_list}."
        return f"Recorded actor(s): {actor_list}."

    if kind == "time":
        times = sorted(record.created_at for record in records)
        if len(times) == 1:
            return f"The matching event was recorded at {times[0].isoformat()}."
        if times:
            qualifier = (
                "The returned records span "
                if total > len(records)
                else "The matching records span "
            )
            return (
                f"{qualifier}{times[0].isoformat()} to "
                f"{times[-1].isoformat()}."
            )

    if kind == "details":
        requested = ", ".join(_requested_detail_terms(query))
        requested_terms = _requested_detail_terms(query)
        if not any(
            term
            in re.sub(r"[^a-z0-9]+", " ", key.casefold()).strip()
            for record in records
            for key in record.details
            for term in requested_terms
        ):
            return f"No matching record contained the requested detail field(s): {requested}."
        return f"Showing matching records with requested detail fields: {requested}."

    return f"Found {total} matching audit record(s). Showing the requested event summaries."


def get_audit_log_agent() -> AuditLogAgent:
    from hawkeye_assistant.hawkeye.audit import get_audit_service

    return AuditLogAgent(get_audit_service())
