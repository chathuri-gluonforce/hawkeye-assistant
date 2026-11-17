"""Tests for the Hawkeye client, using mocked HTTP (no real Hawkeye needed)."""

import json
import logging
import os

import httpx
import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from hawkeye_assistant.hawkeye.client import (  # noqa: E402
    HawkeyeAuthError,
    HawkeyeClient,
    HawkeyeError,
    HawkeyeForbidden,
    HawkeyeUnavailable,
)

pytestmark = pytest.mark.anyio

PASSWORD = "s3cret-password"
COOKIES = {"access_token": "ACCESS-VALUE", "refresh_token": "REFRESH-VALUE"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def client_for(handler, **kwargs) -> HawkeyeClient:
    return HawkeyeClient(
        "http://hawkeye.test", transport=httpx.MockTransport(handler), **kwargs
    )


def reply(status=200, json_body=None, cookies=()):
    headers = [("set-cookie", c) for c in cookies]
    return httpx.Response(status, json=json_body if json_body is not None else {}, headers=headers)


def test_settings_base_url(monkeypatch):
    from hawkeye_assistant.config import Settings

    monkeypatch.delenv("HAWKEYE_BASE_URL", raising=False)
    assert Settings(_env_file=None).hawkeye_base_url == "http://127.0.0.1:8003"

    monkeypatch.setenv("HAWKEYE_BASE_URL", " http://example.test:9000/ ")
    assert Settings(_env_file=None).hawkeye_base_url == "http://example.test:9000"

    monkeypatch.setenv("HAWKEYE_BASE_URL", "example.test")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


async def test_login_sends_credentials_and_returns_cookies():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["cookie"] = request.headers.get("cookie")
        return reply(
            json_body={"role": "supervisor"},
            cookies=["access_token=AAA; HttpOnly; Max-Age=900", "refresh_token=RRR; HttpOnly"],
        )

    result = await client_for(handler).login("ORG1", "sup@example.com", PASSWORD)

    assert seen["path"] == "/auth/login"
    assert seen["body"] == {
        "organization_id": "ORG1",
        "email": "sup@example.com",
        "password": PASSWORD,
    }
    assert seen["cookie"] is None
    assert result.data == {"role": "supervisor"}
    assert result.cookies == {"access_token": "AAA", "refresh_token": "RRR"}
    assert "AAA" not in repr(result)  # tokens stay out of logs and reprs


async def test_expired_cookies_are_ignored():
    def handler(request):
        return reply(cookies=['access_token=""; Max-Age=0', "refresh_token=gone; Max-Age=0"])

    result = await client_for(handler).logout(COOKIES)
    assert result.cookies == {}


async def test_cookies_are_not_shared_between_calls():
    cookie_headers = []

    def handler(request):
        cookie_headers.append(request.headers.get("cookie"))
        return reply(cookies=["access_token=leaked; HttpOnly"])

    client = client_for(handler)
    await client.login("ORG1", "a@example.com", "pw")
    await client.login("ORG2", "b@example.com", "pw")
    assert cookie_headers == [None, None]


async def test_each_call_sends_only_the_cookie_it_needs():
    seen = {}

    def handler(request):
        seen[request.url.path] = request.headers.get("cookie")
        return reply()

    client = client_for(handler)
    await client.me(COOKIES)
    await client.refresh(COOKIES)
    await client.logout(COOKIES)
    await client.list_audit_logs(COOKIES)

    assert seen["/auth/me"] == "access_token=ACCESS-VALUE"
    assert seen["/auth/refresh"] == "refresh_token=REFRESH-VALUE"
    assert seen["/auth/logout"] == "refresh_token=REFRESH-VALUE"
    assert seen["/audit-logs"] == "access_token=ACCESS-VALUE"


async def test_missing_cookie_fails_without_calling_hawkeye():
    calls = []

    def handler(request):
        calls.append(request)
        return reply()

    client = client_for(handler)
    with pytest.raises(HawkeyeAuthError):
        await client.me({})
    with pytest.raises(HawkeyeAuthError):
        await client.refresh({"access_token": "only-access"})
    assert calls == []


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, HawkeyeAuthError), (403, HawkeyeForbidden), (404, HawkeyeError), (500, HawkeyeError)],
)
async def test_http_errors_become_hawkeye_errors(status, error):
    def handler(request):
        return reply(status, {"detail": "nope"})

    with pytest.raises(error) as info:
        await client_for(handler).me(COOKIES)
    assert info.value.status_code == status


@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
async def test_unreachable_or_timeout_raises_unavailable(failure):
    def handler(request):
        raise failure

    with pytest.raises(HawkeyeUnavailable):
        await client_for(handler).me(COOKIES)


async def test_invalid_json_and_redirects_are_errors():
    with pytest.raises(HawkeyeError):
        await client_for(lambda r: httpx.Response(200, content=b"<html>")).me(COOKIES)

    redirect = httpx.Response(302, headers={"location": "http://evil.test/"})
    with pytest.raises(HawkeyeError) as info:
        await client_for(lambda r: redirect).me(COOKIES)
    assert info.value.status_code == 302


async def test_audit_filters_are_sent_and_none_is_skipped():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return reply()

    await client_for(handler).list_audit_logs(
        COOKIES, page=2, action="match.approved", date_from="2026-11-01",
        category=None, automated_only=True,
    )
    assert seen["params"] == {
        "page": "2",
        "action": "match.approved",
        "date_from": "2026-11-01",
        "automated_only": "true",
    }


async def test_audit_id_cannot_change_the_path():
    paths = []

    def handler(request):
        paths.append(request.url.raw_path.decode())
        return reply()

    client = client_for(handler)
    await client.get_audit_log(COOKIES, 42)
    await client.get_audit_log(COOKIES, "../auth/me")
    with pytest.raises(HawkeyeError):
        await client.get_audit_log(COOKIES, "  ")

    assert paths[0] == "/audit-logs/42"
    assert "/auth/me" not in paths[1] and "%2F" in paths[1]
    assert len(paths) == 2


async def test_api_prefix_is_applied():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return reply()

    await client_for(handler, api_prefix="/api/v1/").login("ORG1", "a@example.com", "pw")
    assert paths == ["/api/v1/auth/login"]


async def test_secrets_are_never_logged(caplog):
    def handler(request):
        if request.url.path == "/auth/login":
            return reply(401, {"detail": "Invalid credentials"})
        raise httpx.ConnectError("refused")

    caplog.set_level(logging.DEBUG)
    client = client_for(handler)
    with pytest.raises(HawkeyeAuthError) as info:
        await client.login("ORG1", "sup@example.com", PASSWORD)
    with pytest.raises(HawkeyeUnavailable):
        await client.me(COOKIES)

    everything = caplog.text + str(info.value)
    assert caplog.text
    for secret in (PASSWORD, "ACCESS-VALUE", "REFRESH-VALUE"):
        assert secret not in everything