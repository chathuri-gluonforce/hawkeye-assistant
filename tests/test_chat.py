import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from hawkeye_assistant.agent.audit_query import extract_audit_filters, is_audit_query  # noqa: E402
from hawkeye_assistant.agent.audit_log import AuditLogAgent  # noqa: E402
from hawkeye_assistant.api import routes  # noqa: E402
from hawkeye_assistant.api.app import app  # noqa: E402
from hawkeye_assistant.hawkeye.schemas import AuditPage, SessionInfo, User  # noqa: E402


def test_audit_query_detection_and_filter_extraction():
    query = (
        "Show audit logs for action match_approved from 2026-11-01 to "
        "2026-11-17, automated only, latest 10 records, page 2"
    )

    filters = extract_audit_filters(query, today=date(2026, 11, 17))

    assert is_audit_query(query)
    assert filters.action == "MATCH_APPROVED"
    assert filters.date_from == date(2026, 11, 1)
    assert filters.date_to == date(2026, 11, 17)
    assert filters.automated_only is True
    assert filters.page == 2
    assert filters.page_size == 10


def test_audit_query_supports_relative_dates():
    filters = extract_audit_filters(
        "Show audit logs from the last 7 days", today=date(2026, 11, 17)
    )

    assert filters.date_from == date(2026, 11, 11)
    assert filters.date_to == date(2026, 11, 17)


@pytest.mark.parametrize(
    "query",
    [
        "Show only user created logs",
        "Show user-created audit logs",
        "Show audit logs created by a user",
        "Show human-generated audit records",
        "Show manually created audit logs",
    ],
)
def test_user_created_audit_queries_exclude_automated_records(query):
    assert is_audit_query(query)
    assert extract_audit_filters(query).automated_only is False


def test_audit_query_rejects_unsupported_page_size():
    with pytest.raises(ValueError):
        extract_audit_filters("Show audit logs, latest 500 records")


def test_chat_fetches_existing_audit_records_for_supervisor(monkeypatch):
    class FakeAuth:
        async def current_user(self, session_id):
            assert session_id == "test-session"
            return SimpleNamespace(csrf_token="test-csrf")

    class FakeAuditService:
        async def list_logs(self, session_id, filters):
            assert session_id == "test-session"
            assert filters.action == "MATCH_APPROVED"
            assert filters.automated_only is False
            return AuditPage(items=[], page=1, page_size=20, total=0)

    def unexpected_classification(*args, **kwargs):
        raise AssertionError("Explicit audit requests should bypass customer classification")

    monkeypatch.setattr(routes, "get_auth_service", lambda: FakeAuth())
    monkeypatch.setattr(
        routes, "get_audit_log_agent", lambda: AuditLogAgent(FakeAuditService())
    )
    monkeypatch.setattr(routes, "classify", unexpected_classification)

    with TestClient(app) as client:
        client.cookies.set("assistant_session", "test-session")
        response = client.post(
            "/chat",
            json={
                "text": "Show user-created audit logs for action MATCH_APPROVED"
            },
            headers={"x-csrf-token": "test-csrf"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "audit_results"
    assert response.json()["intent"] == "audit_query"
    assert response.json()["result"]["total"] == 0
    assert response.json()["result"]["answer"] == "No audit records matched your request."


def test_chat_requires_csrf_for_audit_requests(monkeypatch):
    class FakeAuth:
        async def current_user(self, session_id):
            return SimpleNamespace(csrf_token="expected-token")

    monkeypatch.setattr(routes, "get_auth_service", lambda: FakeAuth())

    with TestClient(app) as client:
        client.cookies.set("assistant_session", "test-session")
        response = client.post(
            "/chat",
            json={"text": "Show audit logs"},
        )

    assert response.status_code == 403


def test_chat_preserves_customer_intent_classification(monkeypatch):
    monkeypatch.setattr(
        routes,
        "classify",
        lambda text, prompt, use_memory: ("recon_status", ["lesson-1"]),
    )
    monkeypatch.setattr(
        routes, "resolve_prompt", lambda use_best_prompt: "test prompt"
    )

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"text": "What is the reconciliation status?", "use_memory": False},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "intent"
    assert response.json()["intent"] == "recon_status"
    assert response.json()["lessons"] == []


def test_chat_routes_classifier_audit_intent_to_read_only_service(monkeypatch):
    class FakeAuth:
        async def current_user(self, session_id):
            return SimpleNamespace(csrf_token="test-csrf")

    class FakeAuditService:
        async def list_logs(self, session_id, filters):
            return AuditPage(items=[], page=1, page_size=20, total=0)

    monkeypatch.setattr(
        routes, "classify", lambda text, prompt, use_memory: ("audit_query", [])
    )
    monkeypatch.setattr(routes, "get_auth_service", lambda: FakeAuth())
    monkeypatch.setattr(
        routes, "get_audit_log_agent", lambda: AuditLogAgent(FakeAuditService())
    )

    with TestClient(app) as client:
        client.cookies.set("assistant_session", "test-session")
        response = client.post(
            "/chat",
            json={"text": "Who approved this payment?"},
            headers={"x-csrf-token": "test-csrf"},
        )

    assert response.status_code == 200
    assert response.json()["kind"] == "audit_results"
    assert response.json()["result"]["records"] == []


def test_login_sets_opaque_http_only_session_cookie(monkeypatch):
    session_info = SessionInfo(
        user=User(
            id="user-1",
            organization_id="org-1",
            email="supervisor@example.com",
            role="SUPERVISOR",
        ),
        csrf_token="csrf-token",
        expires_at=datetime.now(UTC) + timedelta(hours=8),
    )

    class FakeSession:
        def info(self):
            return session_info

    class FakeAuth:
        async def login(self, organization_id, email, password):
            assert organization_id == "org-1"
            assert email == "supervisor@example.com"
            assert password == "password"
            return "opaque-session-id", FakeSession()

    monkeypatch.setattr(routes, "get_auth_service", lambda: FakeAuth())

    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            json={
                "organization_id": "org-1",
                "email": "supervisor@example.com",
                "password": "password",
            },
        )

    assert response.status_code == 200
    assert response.json()["csrf_token"] == "csrf-token"
    assert "opaque-session-id" not in response.json()
    assert "assistant_session=opaque-session-id" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()
