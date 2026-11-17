"""Small async client for the Hawkeye backend.

It only sends requests and turns failures into clear errors. Who may do what is
decided by Hawkeye itself.

Safety rules:
- Cookies are passed in per request and handed back, never stored in the client,
  so one user's Hawkeye session can never leak into another user's request.
- Passwords, cookies and tokens are never logged or put in error messages.
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from http.cookiejar import DefaultCookiePolicy
from http.cookies import SimpleCookie
from urllib.parse import quote

import httpx

from hawkeye_assistant.config import get_settings

logger = logging.getLogger(__name__)

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


class HawkeyeError(Exception):
    """Hawkeye said no, or sent something unexpected. See `status_code`."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HawkeyeUnavailable(HawkeyeError):
    """Could not reach Hawkeye (connection failure or timeout)."""


class HawkeyeAuthError(HawkeyeError):
    """401: missing, invalid or expired credentials or session."""


class HawkeyeForbidden(HawkeyeError):
    """403: logged in, but not allowed (for example not a Supervisor)."""


@dataclass(frozen=True)
class HawkeyeResponse:
    data: dict | list | None
    cookies: dict[str, str] = field(default_factory=dict, repr=False)  # secrets!


def _read_set_cookies(response: httpx.Response) -> dict[str, str]:
    """Cookies Hawkeye set. Empty or expired (Max-Age=0) cookies are left out."""
    found: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        parsed: SimpleCookie = SimpleCookie()
        parsed.load(header)
        for name, morsel in parsed.items():
            if morsel.value and morsel["max-age"] != "0":
                found[name] = morsel.value
    return found


class HawkeyeClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_prefix: str = "",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        prefix = api_prefix.strip().strip("/")
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + (f"/{prefix}" if prefix else ""),
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        # Block httpx's built-in cookie jar so cookies are never shared.
        self._http.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- Auth ---
    async def login(self, organization_id: str, email: str, password: str):
        body = {"organization_id": organization_id, "email": email, "password": password}
        return await self._send("POST", "/auth/login", json=body)

    async def me(self, cookies: dict[str, str]):
        return await self._send("GET", "/auth/me", cookies, ACCESS_COOKIE)

    async def refresh(self, cookies: dict[str, str]):
        return await self._send("POST", "/auth/refresh", cookies, REFRESH_COOKIE)

    async def logout(self, cookies: dict[str, str]):
        return await self._send("POST", "/auth/logout", cookies, REFRESH_COOKIE)

    # --- Audit logs (read-only) ---
    async def list_audit_logs(self, cookies: dict[str, str], **filters):
        """Filters: page, page_size, actor_user_id, action, date_from, date_to,
        category, automated_only. Values that are None are skipped."""
        params = {
            key: str(value).lower() if isinstance(value, bool) else str(value)
            for key, value in filters.items()
            if value is not None
        }
        return await self._send("GET", "/audit-logs", cookies, ACCESS_COOKIE, params=params)

    async def get_audit_log(self, cookies: dict[str, str], audit_id: str | int):
        # Percent-encode so an id can never change the request path.
        safe_id = quote(str(audit_id).strip(), safe="")
        if not safe_id:
            raise HawkeyeError("audit_id must not be empty")
        return await self._send("GET", f"/audit-logs/{safe_id}", cookies, ACCESS_COOKIE)

    # --- Internals ---
    async def _send(
        self,
        method: str,
        path: str,
        cookies: dict[str, str] | None = None,
        cookie_name: str | None = None,
        **kwargs,
    ) -> HawkeyeResponse:
        headers = {}
        if cookie_name:  # send only the one cookie this call needs
            value = (cookies or {}).get(cookie_name)
            if not value or any(c in value for c in ";\r\n"):
                raise HawkeyeAuthError("Missing or invalid Hawkeye session")
            headers["Cookie"] = f"{cookie_name}={value}"

        try:
            response = await self._http.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:  # timeouts and connection failures
            logger.warning("Hawkeye %s %s failed: %s", method, path, type(exc).__name__)
            raise HawkeyeUnavailable("Hawkeye is unreachable or timed out") from exc

        logger.debug("Hawkeye %s %s -> %s", method, path, response.status_code)
        status = response.status_code
        if status == 401:
            raise HawkeyeAuthError("Hawkeye rejected the credentials or session", status)
        if status == 403:
            raise HawkeyeForbidden("Hawkeye denied access", status)
        if not response.is_success:
            raise HawkeyeError(f"Hawkeye returned status {status}", status)

        data = None
        if response.content:
            try:
                data = response.json()
            except ValueError as exc:
                raise HawkeyeError("Hawkeye returned invalid JSON", status) from exc
        return HawkeyeResponse(data, _read_set_cookies(response))


@lru_cache
def get_hawkeye_client() -> HawkeyeClient:
    """Shared client built from settings. Close it when the app shuts down."""
    s = get_settings()
    return HawkeyeClient(
        s.hawkeye_base_url,
        api_prefix=s.hawkeye_api_prefix,
        timeout=s.hawkeye_timeout_seconds,
    )