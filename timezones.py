"""
Per-user timezone helpers (Phase 1 of the timezone work).

SINGLE RESPONSIBILITY: decide what "now", "today", "this week" and "this month"
mean for a given user. Every period calculation in the app should go through
here instead of calling date.today() / datetime.now(), which use whatever
timezone the server happens to run in.

Timestamps stay absolute (UTC). Only the *interpretation* of a period depends on
the user's IANA timezone setting (e.g. "Africa/Lagos", "Asia/Kolkata").
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Existing users were all treated as Lagos time before this setting existed.
DEFAULT_TIMEZONE = "Africa/Lagos"

_LAGOS_FALLBACK = timezone(timedelta(hours=1))  # WAT has no daylight saving


def is_valid_timezone(name) -> bool:
    if not name or not isinstance(name, str):
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False


def resolve_tz(name=None):
    """Return a tzinfo for an IANA name, falling back to the default."""
    for candidate in (name, DEFAULT_TIMEZONE):
        if is_valid_timezone(candidate):
            return ZoneInfo(candidate)
    return _LAGOS_FALLBACK


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def local_now(tz_name=None) -> datetime:
    """Timezone-aware 'now' in the user's timezone."""
    return utc_now().astimezone(resolve_tz(tz_name))


def local_today(tz_name=None) -> date:
    return local_now(tz_name).date()


def period_bounds(tz_name=None) -> dict:
    """Start dates (in the user's timezone) for today, this week and this month.

    Weeks start on Monday. Callers compare a transaction's local date against
    these: `d == today`, `d >= week_start`, `d >= month_start`.
    """
    today = local_today(tz_name)
    return {
        "timezone": tz_name if is_valid_timezone(tz_name) else DEFAULT_TIMEZONE,
        "today": today,
        "week_start": today - timedelta(days=today.weekday()),
        "month_start": today.replace(day=1),
    }
