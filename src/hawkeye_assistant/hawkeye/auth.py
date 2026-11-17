"""Supervisor login and server-side sessions.

Hawkeye stays the source of truth: it checks the password and the role. The
assistant only keeps the Hawkeye cookies on the server, and gives the browser an
opaque session id. Sessions live in memory, so they are lost when the server
restarts (fine for now; the store can be swapped later).
"""

import asyncio
import hashlib
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from pydantic import ValidationError

from hawkeye_assistant.config import get_settings
from hawkeye_assistant.hawkeye.client import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    HawkeyeAuthError,
    HawkeyeClient,
    HawkeyeError,
    HawkeyeResponse,
    get_hawkeye_client,
)
from hawkeye_assistant.hawkeye.schemas import SessionInfo, User

logger = logging.getLogger(__name__)

SUPERVISOR_ROLE = "SUPERVISOR"


class NotSupervisor(Exception):
    """The user is not an active Supervisor."""


class SessionExpired(Exception):
    """No valid assistant session (missing, unknown, expired or ended)."""


@dataclass
class Session:
    user: User
    cookies: dict[str, str] = field(repr=False)  # Hawkeye tokens: never expose
    csrf_token: str = field(repr=False)
    expires_at: datetime
    dead: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def info(self) -> SessionInfo:
        return SessionInfo(
            user=self.user, csrf_token=self.csrf_token, expires_at=self.expires_at
        )


def _key(session_id: str) -> str:
    """Sessions are stored under a hash, so the raw id is never kept."""
    return hashlib.sha256(session_id.encode()).hexdigest()


def _parse_user(data: object) -> User:
    try:
        return User.model_validate(data)
    except ValidationError as exc:
        raise HawkeyeError("Hawkeye returned an unexpected user profile") from exc


def _is_active_supervisor(user: User) -> bool:
    return user.is_active and user.role == SUPERVISOR_ROLE


class AuthService:
    def __init__(self, client: HawkeyeClient, session_hours: float = 8.0) -> None:
        self._client = client
        self._lifetime = timedelta(hours=session_hours)
        self._sessions: dict[str, Session] = {}

    # --- Login / logout ---
    async def login(
        self, organization_id: str, email: str, password: str
    ) -> tuple[str, Session]:
        """Returns (session_id, session). The password is not kept."""
        response = await self._client.login(organization_id, email, password)
        user = _parse_user(response.data)

        if not _is_active_supervisor(user):
            await self._revoke(response.cookies)  # end the Hawkeye session we just made
            raise NotSupervisor("Supervisor login required")

        cookies = {
            name: response.cookies[name]
            for name in (ACCESS_COOKIE, REFRESH_COOKIE)
            if name in response.cookies
        }
        if len(cookies) != 2:
            await self._revoke(response.cookies)
            raise HawkeyeError("Hawkeye login did not return session cookies")

        await self._purge_expired()
        session_id = secrets.token_urlsafe(32)
        session = Session(
            user=user,
            cookies=cookies,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + self._lifetime,
        )
        self._sessions[_key(session_id)] = session
        return session_id, session

    async def logout(self, session_id: str | None) -> None:
        if session_id:
            await self._drop(_key(session_id), revoke=True)

    # --- Sessions ---
    async def get(self, session_id: str | None) -> Session:
        """The live session for this id, or SessionExpired."""
        key = _key(session_id) if session_id else ""
        session = self._sessions.get(key)
        if session is None:
            raise SessionExpired("No valid session")
        if session.expires_at <= datetime.now(UTC):
            await self._drop(key, revoke=True)
            raise SessionExpired("Session expired")
        return session

    async def current_user(self, session_id: str | None) -> Session:
        """Check with Hawkeye that the user is still an active Supervisor."""
        await self.get(session_id)
        response = await self.call(session_id, self._client.me)
        user = _parse_user(response.data)
        if not _is_active_supervisor(user):
            await self._drop(_key(session_id), revoke=True)
            raise NotSupervisor("Supervisor login required")
        session = await self.get(session_id)
        session.user = user
        return session

    async def call(
        self,
        session_id: str | None,
        operation: Callable[[dict[str, str]], Awaitable[HawkeyeResponse]],
    ) -> HawkeyeResponse:
        """Run a Hawkeye call with this session's cookies.

        If the access token has expired (401), refresh once and retry once.
        """
        session = await self.get(session_id)
        key = _key(session_id)
        used_access = session.cookies[ACCESS_COOKIE]
        try:
            return await operation(session.cookies)
        except HawkeyeAuthError:
            pass

        await self._refresh(key, session, used_access)
        try:
            return await operation(session.cookies)
        except HawkeyeAuthError as exc:
            await self._drop(key, revoke=True)
            raise SessionExpired("Hawkeye session ended") from exc

    # --- Internals ---
    async def _refresh(self, key: str, session: Session, used_access: str) -> None:
        # Hawkeye rotates refresh tokens, so only one refresh may run at a time.
        async with session.lock:
            if session.dead:
                raise SessionExpired("Session ended")
            if session.cookies[ACCESS_COOKIE] != used_access:
                return  # another request already refreshed it
            try:
                response = await self._client.refresh(session.cookies)
            except HawkeyeAuthError as exc:
                await self._drop(key, revoke=False)
                raise SessionExpired("Hawkeye session expired") from exc
            if ACCESS_COOKIE not in response.cookies or REFRESH_COOKIE not in response.cookies:
                raise HawkeyeError("Hawkeye refresh did not return new cookies")
            for name in (ACCESS_COOKIE, REFRESH_COOKIE):
                session.cookies[name] = response.cookies[name]

    async def _drop(self, key: str, *, revoke: bool) -> None:
        session = self._sessions.pop(key, None)
        if session is None:
            return
        session.dead = True
        if revoke:
            await self._revoke(session.cookies)

    async def _revoke(self, cookies: dict[str, str]) -> None:
        """Ask Hawkeye to end a session. A failure is logged, not hidden."""
        if REFRESH_COOKIE not in cookies:
            return
        try:
            await self._client.logout(cookies)
        except HawkeyeError as exc:
            logger.warning("Could not end Hawkeye session: %s", type(exc).__name__)

    async def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        for key, session in list(self._sessions.items()):
            if session.expires_at <= now:
                await self._drop(key, revoke=True)


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService(get_hawkeye_client(), get_settings().assistant_session_hours)