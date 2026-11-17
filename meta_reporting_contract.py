"""Shared read/reporting contract. No credentials, network or database access."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re

REPORTABLE_CAMPAIGN_STATUSES = ("ACTIVE", "PAUSED", "ARCHIVED")
REPORTABLE_ADSET_STATUSES = (*REPORTABLE_CAMPAIGN_STATUSES, "CAMPAIGN_PAUSED", "IN_PROCESS", "WITH_ISSUES")
REPORTABLE_AD_STATUSES = (*REPORTABLE_ADSET_STATUSES, "ADSET_PAUSED", "DISAPPROVED", "PENDING_REVIEW")


def validate_account(account, account_id):
    if not isinstance(account, dict) or str(account.get("account_id") or account.get("id") or "").removeprefix("act_") != str(account_id).removeprefix("act_"):
        raise ValueError("Meta returned a different or missing account identity; history was retained.")
    if not re.fullmatch(r"[A-Z]{3}", str(account.get("currency") or "")):
        raise ValueError("Meta account currency is unavailable; history was retained.")
    try:
        ZoneInfo(account["timezone_name"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Meta account timezone is unavailable; history was retained.") from None
    return account


def reporting_window(account, since=None, until=None, *, days=None, at=None):
    today = (at or datetime.now(timezone.utc)).astimezone(ZoneInfo(account["timezone_name"])).date()
    if days is not None:
        if since is not None or until is not None or type(days) is not int or not 1 <= days <= 31:
            raise ValueError("Choose 1–31 completed account-calendar days.")
        until = today - timedelta(days=1)
        since = until - timedelta(days=int(days)-1)
    else:
        since = date.fromisoformat(str(since)) if since is not None else today-timedelta(days=1)
        until = date.fromisoformat(str(until)) if until is not None else since
    if until < since or (until-since).days >= 31 or until >= today:
        raise ValueError("Reporting refresh requires 1–31 completed account-calendar days.")
    return since.isoformat(), until.isoformat()
