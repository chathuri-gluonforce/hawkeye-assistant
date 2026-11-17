"""Tests for the read-only audit service, against a fake Hawkeye (no network)."""

import os
from datetime import date

import httpx
import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from hawkeye_assistant.hawkeye.audit import AuditService, InvalidAuditId  # noqa: E402
from hawkeye_assistant.hawkeye.auth import (  # noqa: E402
    AuthService,
    NotSupervisor,
    SessionExpired,
)
from hawkeye_assistant.hawkeye.client import (  # noqa: E402
    HawkeyeClient,
    HawkeyeError,
    HawkeyeForbidden,
    HawkeyeUnavailable,
)
from hawkeye_assistant.hawkeye.schemas import AuditFilters, AuditRecord  # noqa: E402

pytestmark = pytest.mark.anyio

HUMAN = {
    "id": "7721a414-8063-4bdf-a33e-9ce4216393ef",
    "organization_id": "org-1",
    "entity_type": "reconciliation_match",
    "entity_id": "f1d1eb26-42cc-4c81-b5ed-a52b27be07ad",
    "action": "MATCH_APPROVED",
    "details": {"match_type": "AI_SUGGESTED", "amount_cents": -500000, "currency": "LKR"},
    "actor_user_id": "b436b9f8-8cd0-4563-9af8-bfde9394040c",
    "actor_role": "SUPERVISOR",
    "actor_full_name": "Sam Taylor",
    "actor_email": "sam@example.com",
    "created_at": "2026-10-30T16:54:10.615446",
}
AUTOMATED = {
    **HUMAN,
    "id": "a3f2f864-4886-44e2-a065-13b94f0908c7",
    "action": "MATCH_CREATED",
    "details": {"match_type": "DETERMINISTIC"},
    "actor_user_id": None,
    "actor_role": None,
    "actor_full_name": None,
    "actor_email": None,
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def reply(status=200, body=None, cookies=()):
    headers = [("set-cookie", c) for c in cookies]
    return httpx.Response(status, json=body if body is not None else {}, headers=headers)


class FakeHawkeye:
    def __init__(self, items=None):
        self.items = items if items is not None else [HUMAN, AUTOMATED]
        self.total = len(self.items)
        self.access = "access-0"
        self.audit_requests: list[httpx.Request] = []
        self.audit_status = 200
        self.audit_body = None  # overrides the response body
        self.record = HUMAN
        self.down = False
        self.refreshes = 0

    def __call__(self, request):
        path = request.url.path.removeprefix("/api/v1")
        sent = request.headers.get("cookie", "")
        if path == "/auth/login":
            profile = {"id": "u1", "organization_id": "org-1", "email": "sam@example.com",
                       "full_name": "Sam", "role": "SUPERVISOR", "is_active": True}
            return reply(200, profile, [
                "access_token=access-0; HttpOnly; Path=/",
                "refresh_token=refresh-0; HttpOnly; Path=/api/v1/auth",
            ])
        if path == "/auth/refresh":
            self.refreshes += 1
            self.access = "access-1"
            return reply(200, {}, ["access_token=access-1; Path=/", "refresh_token=refresh-1; Path=/"])
        if path == "/auth/logout":
            return reply(200)
        if path.startswith("/audit-logs"):
            self.audit_requests.append(request)
            if self.down:
                raise httpx.ConnectError("refused")
            if sent != f"access_token={self.access}":
                return reply(401, {"detail": "expired"})
            if self.audit_status != 200:
                return reply(self.audit_status, {"detail": "no"})
            if self.audit_body is not None:
                return reply(200, self.audit_body)
            if path == "/audit-logs":
                params = request.url.params
                return reply(200, {
                    "items": self.items,
                    "page": int(params.get("page", 1)),
                    "page_size": int(params.get("page_size", 20)),
                    "total": self.total,
                })
            return reply(200, self.record)
        return reply(404)


async def setup(fake: FakeHawkeye):
    client = HawkeyeClient(
        "http://hawkeye.test", api_prefix="/api/v1", transport=httpx.MockTransport(fake)
    )
    auth = AuthService(client)
    session_id, session = await auth.login("org-1", "sam@example.com", "pw")
    return AuditService(auth, client), session_id, session


# -------------------------------------------------------------------- list
async def test_list_returns_structured_records_and_flags_automated():
    service, session_id, _ = await setup(FakeHawkeye())

    page = await service.list_logs(session_id)

    assert [r.action for r in page.items] == ["MATCH_APPROVED", "MATCH_CREATED"]
    assert [r.automated for r in page.items] == [False, True]
    assert page.items[0].actor_full_name == "Sam Taylor"
    assert page.total == 2 and page.has_more is False
    assert page.model_dump(mode="json")["items"][1]["automated"] is True


async def test_pagination_values_are_sent_and_has_more_is_computed():
    fake = FakeHawkeye()
    fake.total = 12
    service, session_id, _ = await setup(fake)

    page2 = await service.list_logs(session_id, AuditFilters(page=2, page_size=5))
    page3 = await service.list_logs(session_id, AuditFilters(page=3, page_size=5))

    assert dict(fake.audit_requests[0].url.params) == {"page": "2", "page_size": "5"}
    assert page2.has_more is True
    assert page3.has_more is False


async def test_filters_are_sent_to_hawkeye():
    fake = FakeHawkeye()
    service, session_id, _ = await setup(fake)

    await service.list_logs(
        session_id,
        AuditFilters(
            action="match_approved",
            category="matching",
            actor_user_id="b436b9f8-8cd0-4563-9af8-bfde9394040c",
            date_from=date(2026, 11, 1),
            date_to=date(2026, 11, 17),
            automated_only=False,
        ),
    )

    assert dict(fake.audit_requests[0].url.params) == {
        "page": "1",
        "page_size": "20",
        "action": "MATCH_APPROVED",
        "category": "matching",
        "actor_user_id": "b436b9f8-8cd0-4563-9af8-bfde9394040c",
        "date_from": "2026-11-01",
        "date_to": "2026-11-17",
        "automated_only": "false",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "x; DROP TABLE"},
        {"category": "../etc"},
        {"actor_user_id": "a/b"},
        {"page_size": 500},
        {"page": 0},
        {"date_from": date(2026, 11, 17), "date_to": date(2026, 11, 1)},
        {"url": "http://evil.test"},  # unknown fields are refused
    ],
)
def test_bad_filters_are_rejected_before_reaching_hawkeye(bad):
    with pytest.raises(ValueError):
        AuditFilters(**bad)


# --------------------------------------------------------------------- get
async def test_get_one_record_with_details():
    service, session_id, _ = await setup(FakeHawkeye())

    record = await service.get_log(session_id, HUMAN["id"])

    assert record.id == HUMAN["id"]
    assert record.details["currency"] == "LKR"
    assert record.automated is False


@pytest.mark.parametrize("bad_id", ["", "../auth/me", "a/b", "x" * 100, "id with space"])
async def test_invalid_audit_id_never_reaches_hawkeye(bad_id):
    fake = FakeHawkeye()
    service, session_id, _ = await setup(fake)

    with pytest.raises(InvalidAuditId):
        await service.get_log(session_id, bad_id)
    assert fake.audit_requests == []


async def test_missing_record_is_a_404_error():
    fake = FakeHawkeye()
    fake.audit_status = 404
    service, session_id, _ = await setup(fake)

    with pytest.raises(HawkeyeError) as info:
        await service.get_log(session_id, "does-not-exist")
    assert info.value.status_code == 404


# ------------------------------------------------------------ access rules
@pytest.mark.parametrize("session_id", [None, "", "not-a-real-session"])
async def test_no_valid_session_means_no_hawkeye_call(session_id):
    fake = FakeHawkeye()
    service, _, _ = await setup(fake)

    with pytest.raises(SessionExpired):
        await service.list_logs(session_id)
    with pytest.raises(SessionExpired):
        await service.get_log(session_id, HUMAN["id"])
    assert fake.audit_requests == []


async def test_non_supervisor_session_is_refused_locally():
    fake = FakeHawkeye()
    service, session_id, session = await setup(fake)
    session.user.role = "ASSISTANT"  # even if a session were somehow tampered with

    with pytest.raises(NotSupervisor):
        await service.list_logs(session_id)
    with pytest.raises(NotSupervisor):
        await service.get_log(session_id, HUMAN["id"])
    assert fake.audit_requests == []


async def test_hawkeye_403_is_passed_on():
    fake = FakeHawkeye()
    fake.audit_status = 403
    service, session_id, _ = await setup(fake)

    with pytest.raises(HawkeyeForbidden):
        await service.list_logs(session_id)


async def test_records_from_another_organization_are_rejected():
    other = {**HUMAN, "organization_id": "org-2"}
    fake = FakeHawkeye(items=[HUMAN, other])
    fake.record = other
    service, session_id, _ = await setup(fake)

    with pytest.raises(HawkeyeError):
        await service.list_logs(session_id)
    with pytest.raises(HawkeyeError):
        await service.get_log(session_id, other["id"])


# ---------------------------------------------------------------- failures
async def test_hawkeye_unavailable():
    fake = FakeHawkeye()
    service, session_id, _ = await setup(fake)
    fake.down = True

    with pytest.raises(HawkeyeUnavailable):
        await service.list_logs(session_id)


async def test_expired_access_token_is_refreshed_automatically():
    fake = FakeHawkeye()
    service, session_id, _ = await setup(fake)
    fake.access = "expired-on-server"

    page = await service.list_logs(session_id)

    assert page.total == 2
    assert fake.refreshes == 1


@pytest.mark.parametrize("body", [{"items": "nope"}, {"unexpected": True}, []])
async def test_unexpected_hawkeye_response_is_an_error(body):
    fake = FakeHawkeye()
    fake.audit_body = body
    service, session_id, _ = await setup(fake)

    with pytest.raises(HawkeyeError):
        await service.list_logs(session_id)


# ------------------------------------------------------------------ models
def test_record_without_actor_is_automated():
    assert AuditRecord.model_validate(AUTOMATED).automated is True
    assert AuditRecord.model_validate(HUMAN).automated is False
    assert AuditRecord.model_validate({**HUMAN, "details": None}).details == {}