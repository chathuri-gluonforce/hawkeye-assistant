"""Read-only access to Hawkeye audit logs for a logged-in Supervisor.

There is no way to create, change or delete audit records here. Only the two
fixed Hawkeye read endpoints are used, and the caller only supplies validated
filters, never a URL.
"""

import logging
import re
from functools import lru_cache

from pydantic import BaseModel, ValidationError

from hawkeye_assistant.hawkeye.auth import (
    SUPERVISOR_ROLE,
    AuthService,
    NotSupervisor,
    Session,
    get_auth_service,
)
from hawkeye_assistant.hawkeye.client import (
    HawkeyeClient,
    HawkeyeError,
    get_hawkeye_client,
)
from hawkeye_assistant.hawkeye.schemas import AuditFilters, AuditPage, AuditRecord

logger = logging.getLogger(__name__)

_AUDIT_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class InvalidAuditId(ValueError):
    """The audit id is not in a valid format."""


def _parse[T: BaseModel](model: type[T], data: object) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        # Log where it failed, not the data itself.
        logger.warning("Unexpected audit response: %s", [e["loc"] for e in exc.errors()])
        raise HawkeyeError("Hawkeye returned an unexpected audit response") from None


class AuditService:
    def __init__(self, auth: AuthService, client: HawkeyeClient) -> None:
        self._auth = auth
        self._client = client

    async def list_logs(
        self, session_id: str | None, filters: AuditFilters | None = None
    ) -> AuditPage:
        session = await self._supervisor_session(session_id)
        params = (filters or AuditFilters()).model_dump(mode="json", exclude_none=True)

        response = await self._auth.call(
            session_id, lambda cookies: self._client.list_audit_logs(cookies, **params)
        )
        page = _parse(AuditPage, response.data)
        for record in page.items:
            self._check_tenant(session, record)
        return page

    async def get_log(self, session_id: str | None, audit_id: str) -> AuditRecord:
        if not _AUDIT_ID.match(audit_id or ""):
            raise InvalidAuditId("Invalid audit id")
        session = await self._supervisor_session(session_id)

        response = await self._auth.call(
            session_id, lambda cookies: self._client.get_audit_log(cookies, audit_id)
        )
        record = _parse(AuditRecord, response.data)
        self._check_tenant(session, record)
        return record

    async def _supervisor_session(self, session_id: str | None) -> Session:
        session = await self._auth.get(session_id)  # raises SessionExpired
        if session.user.role != SUPERVISOR_ROLE:
            raise NotSupervisor("Supervisor login required")
        return session

    @staticmethod
    def _check_tenant(session: Session, record: AuditRecord) -> None:
        """Hawkeye already scopes by organization; this is a second safety net."""
        if record.organization_id != session.user.organization_id:
            logger.error("Hawkeye returned an audit record from another organization")
            raise HawkeyeError("Hawkeye returned a record from another organization")


@lru_cache
def get_audit_service() -> AuditService:
    return AuditService(get_auth_service(), get_hawkeye_client())