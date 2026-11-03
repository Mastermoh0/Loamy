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


def has_time_component(value) -> bool:
    """True when a value carries a time of day, not just a calendar date."""
    if isinstance(value, datetime):
        return True
    text = str(value or "")
    return "T" in text or ":" in text


def to_utc(value, tz_name=None):
    """Convert a datetime or ISO string to an aware UTC datetime, or None.

    Values without an offset are read as wall-clock time in `tz_name`. Plain
    dates (no time of day) return None because they are not an instant."""
    if value is None or value == "" or not has_time_component(value):
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=resolve_tz(tz_name))
    return moment.astimezone(timezone.utc)


def to_utc_iso(value, tz_name=None):
    moment = to_utc(value, tz_name)
    return moment.isoformat() if moment else None


def epoch_ms_to_utc_iso(ms):
    """Gmail's internalDate (epoch milliseconds) as a UTC ISO string."""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def entry_instant_iso(date_iso, tz_name=None) -> str:
    """Best-guess instant for an entry that only has a date.

    Logged for today: the moment of logging. Backdated: noon on that day in the
    user's timezone, so it can never slip across a day boundary. Either way the
    time of day is an estimate, so callers store time_known = False."""
    today = local_today(tz_name)
    try:
        day = date.fromisoformat(str(date_iso)[:10])
    except ValueError:
        day = today
    if day == today:
        return utc_now().isoformat()
    noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=resolve_tz(tz_name))
    return noon.astimezone(timezone.utc).isoformat()


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
