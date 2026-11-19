"""Local detection and extraction for read-only Hawkeye audit queries."""

import re
from datetime import date, timedelta

from hawkeye_assistant.hawkeye.schemas import AuditFilters

_AUDIT_REQUEST = re.compile(
    r"\baudit(?:\s+(?:logs?|trail|history))?\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_ACTION = re.compile(
    r"\baction(?:\s+(?:is|=|:))?\s+([A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_CATEGORY = re.compile(
    r"\bcategory(?:\s+(?:is|=|:))?\s+([A-Za-z][A-Za-z0-9_-]*)",
    re.IGNORECASE,
)
_ACTOR_ID = re.compile(
    r"\b(?:actor|user)(?:\s+user)?\s+id(?:\s+is|=|:)?\s+([A-Za-z0-9-]{1,64})",
    re.IGNORECASE,
)
_USER_ACTIVITY = re.compile(
    r"\b(?:"
    r"user[- ](?:created|generated|performed|made)|"
    r"(?:created|generated|performed|made)\s+by\s+(?:a\s+)?users?|"
    r"human[- ](?:created|generated|performed|made)|"
    r"manually\s+(?:created|generated|performed|made)"
    r")\b",
    re.IGNORECASE,
)


def is_audit_query(text: str) -> bool:
    return bool(
        _AUDIT_REQUEST.search(text)
        or (_USER_ACTIVITY.search(text) and re.search(r"\blogs?\b", text, re.IGNORECASE))
    )


def extract_audit_filters(text: str, *, today: date | None = None) -> AuditFilters:
    """Extract supported filters locally; audit-query text is not sent to an LLM."""
    today = today or date.today()
    query = text.casefold()
    values: dict[str, object] = {}

    dates = [date.fromisoformat(value) for value in _ISO_DATE.findall(text)]
    if len(dates) >= 2:
        values["date_from"], values["date_to"] = dates[:2]
    elif len(dates) == 1:
        if "since" in query or "after" in query:
            values["date_from"] = dates[0]
        else:
            values["date_from"] = values["date_to"] = dates[0]
    elif "yesterday" in query:
        yesterday = today - timedelta(days=1)
        values["date_from"] = values["date_to"] = yesterday
    elif "today" in query:
        values["date_from"] = values["date_to"] = today
    else:
        days = re.search(r"\blast\s+(\d+)\s+days?\b", query)
        if days:
            count = int(days.group(1))
            if not 1 <= count <= 366:
                raise ValueError("Audit date ranges must be between 1 and 366 days")
            values["date_from"] = today - timedelta(days=count - 1)
            values["date_to"] = today

    if match := _ACTION.search(text):
        values["action"] = match.group(1)
    if match := _CATEGORY.search(text):
        values["category"] = match.group(1)
    if match := _ACTOR_ID.search(text):
        values["actor_user_id"] = match.group(1)

    if re.search(r"\bautomated(?:\s+only)?\b|\bsystem[- ]generated\b", query):
        values["automated_only"] = True
    elif re.search(r"\bhuman(?:\s+only)?\b", query) or _USER_ACTIVITY.search(text) or re.search(
        r"\buser[- ]performed\b", query
    ):
        values["automated_only"] = False

    if match := re.search(r"\bpage\s+(\d+)\b", query):
        values["page"] = int(match.group(1))
    if match := re.search(
        r"\b(?:last|latest)\s+(\d+)\s+(?:audit\s+)?(?:logs?|records?)\b", query
    ):
        values["page_size"] = int(match.group(1))

    return AuditFilters.model_validate(values)
