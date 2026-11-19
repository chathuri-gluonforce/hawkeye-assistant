"""Authentication and chat endpoints for the Hawkeye-backed assistant."""

import secrets
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Request, Response

from hawkeye_assistant.agent.audit_log import get_audit_log_agent
from hawkeye_assistant.agent.audit_query import is_audit_query
from hawkeye_assistant.agent.classify import classify, resolve_prompt
from hawkeye_assistant.api.schemas import (
    AuditAnswerResponse,
    AuditChatResponse,
    AuditRecordSummaryResponse,
    ChatRequest,
    ChatResponse,
    IntentChatResponse,
    LoginRequest,
    LoginResponse,
)
from hawkeye_assistant.config import get_settings
from hawkeye_assistant.hawkeye.auth import (
    NotSupervisor,
    Session,
    SessionExpired,
    get_auth_service,
)
from hawkeye_assistant.hawkeye.client import (
    HawkeyeAuthError,
    HawkeyeError,
    HawkeyeForbidden,
    HawkeyeUnavailable,
)
from hawkeye_assistant.memory import store as memory

router = APIRouter()
SESSION_COOKIE = "assistant_session"
CSRF_HEADER = "x-csrf-token"


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, (SessionExpired, HawkeyeAuthError)):
        raise HTTPException(status_code=401, detail="Please sign in again") from error
    if isinstance(error, (NotSupervisor, HawkeyeForbidden)):
        raise HTTPException(status_code=403, detail="Supervisor access is required") from error
    if isinstance(error, HawkeyeUnavailable):
        raise HTTPException(
            status_code=503, detail="Hawkeye is temporarily unavailable"
        ) from error
    if isinstance(error, HawkeyeError):
        raise HTTPException(status_code=502, detail="Hawkeye request failed") from error
    raise error


def _check_csrf(request: Request, session: Session) -> None:
    token = request.headers.get(CSRF_HEADER, "")
    if not secrets.compare_digest(token, session.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=int(settings.assistant_session_hours * 60 * 60),
        httponly=True,
        secure=settings.assistant_cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        session_id, session = await get_auth_service().login(
            payload.organization_id,
            payload.email,
            payload.password.get_secret_value(),
        )
    except (NotSupervisor, HawkeyeError) as error:
        _raise_http_error(error)
    _set_session_cookie(response, session_id)
    return LoginResponse(**session.info().model_dump())


@router.get("/auth/me", response_model=LoginResponse)
async def current_session(request: Request, response: Response) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    session_id = request.cookies.get(SESSION_COOKIE)
    try:
        session = await get_auth_service().current_user(session_id)
    except (SessionExpired, NotSupervisor, HawkeyeError) as error:
        _raise_http_error(error)
    return LoginResponse(**session.info().model_dump())


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    session_id = request.cookies.get(SESSION_COOKIE)
    auth = get_auth_service()
    if session_id:
        try:
            session = await auth.get(session_id)
        except SessionExpired:
            pass
        else:
            _check_csrf(request, session)
        await auth.logout(session_id)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    response.status_code = 204
    return response


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, request: Request, response: Response
) -> ChatResponse:
    response.headers["Cache-Control"] = "no-store"
    intent = "audit_query"
    if not is_audit_query(payload.text) and payload.filters is None:
        prompt = resolve_prompt(payload.use_best_prompt)
        intent, used_ids = classify(
            payload.text, prompt, use_memory=payload.use_memory
        )
        if intent != "audit_query":
            lessons = memory.lessons_by_ids(used_ids) if payload.use_memory else []
            return IntentChatResponse(
                text=payload.text,
                intent=intent,
                prompt=prompt,
                lessons=lessons,
            )

    session_id = request.cookies.get(SESSION_COOKIE)
    try:
        session = await get_auth_service().current_user(session_id)
        _check_csrf(request, session)
        answer = await get_audit_log_agent().answer(
            payload.text, session_id, payload.filters
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (SessionExpired, NotSupervisor, HawkeyeError) as error:
        _raise_http_error(error)

    return AuditChatResponse(
        intent="audit_query",
        result=AuditAnswerResponse(
            answer=answer.answer,
            filters=answer.filters,
            records=[
                AuditRecordSummaryResponse(
                    id=record.id,
                    action=record.action,
                    entity_type=record.entity_type,
                    entity_id=record.entity_id,
                    actor_name=record.actor_name,
                    actor_email=record.actor_email,
                    actor_role=record.actor_role,
                    created_at=record.created_at,
                    automated=record.automated,
                    details=record.details,
                )
                for record in answer.records
            ],
            page=answer.page,
            page_size=answer.page_size,
            total=answer.total,
            has_more=answer.has_more,
        ),
    )