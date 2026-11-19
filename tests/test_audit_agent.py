from datetime import datetime

import pytest

from hawkeye_assistant.agent.audit_log import AuditLogAgent
from hawkeye_assistant.hawkeye.schemas import AuditPage, AuditRecord


def audit_record(**updates):
    record = {
        "id": "audit-1",
        "organization_id": "org-1",
        "entity_type": "reconciliation_match",
        "entity_id": "match-1",
        "action": "MATCH_APPROVED",
        "details": {
            "amount_cents": 5000,
            "currency": "LKR",
            "match_type": "AI_SUGGESTED",
        },
        "actor_user_id": "user-1",
        "actor_role": "SUPERVISOR",
        "actor_full_name": "Sam Taylor",
        "actor_email": "sam@example.com",
        "created_at": datetime(2026, 11, 17, 10, 30),
    }
    return AuditRecord.model_validate({**record, **updates})


class FakeAuditService:
    def __init__(self, items=None, total=None):
        self.items = items or [audit_record()]
        self.total = len(self.items) if total is None else total
        self.filters = None

    async def list_logs(self, session_id, filters):
        self.filters = filters
        return AuditPage(
            items=self.items,
            page=filters.page,
            page_size=filters.page_size,
            total=self.total,
        )


@pytest.mark.anyio
async def test_user_created_count_is_answered_without_returning_records():
    service = FakeAuditService(total=5)

    answer = await AuditLogAgent(service).answer(
        "How many user created logs?", "session"
    )

    assert service.filters.automated_only is False
    assert answer.answer == "Found 5 user-performed audit record(s)."
    assert answer.records == []


@pytest.mark.anyio
async def test_default_answer_returns_summaries_without_raw_details():
    answer = await AuditLogAgent(FakeAuditService()).answer(
        "Show user-created audit logs", "session"
    )

    assert answer.records[0].action == "MATCH_APPROVED"
    assert answer.records[0].actor_name == "Sam Taylor"
    assert answer.records[0].details == {}


@pytest.mark.anyio
async def test_only_requested_detail_fields_are_returned():
    answer = await AuditLogAgent(FakeAuditService()).answer(
        "Show the amount in the audit log", "session"
    )

    assert answer.records[0].details == {"amount_cents": 5000}


@pytest.mark.anyio
async def test_actor_question_is_answered_from_matching_records():
    answer = await AuditLogAgent(FakeAuditService()).answer(
        "Who performed the audit action?", "session"
    )

    assert answer.answer == "Recorded actor(s): Sam Taylor."
