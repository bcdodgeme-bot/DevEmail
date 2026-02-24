"""
Recurrence Rule (RRULE) Service

Parses iCalendar RRULE strings and expands them into concrete
event occurrences within a given date range.

Supports: DAILY, WEEKLY, MONTHLY, YEARLY frequencies
with INTERVAL, COUNT, UNTIL, BYDAY constraints.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

WEEKDAY_MAP = {
    "MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6,
}

WEEKDAY_NAMES = {
    "MO": "Monday", "TU": "Tuesday", "WE": "Wednesday",
    "TH": "Thursday", "FR": "Friday", "SA": "Saturday", "SU": "Sunday",
}


def parse_rrule(rrule_str: str) -> dict:
    """Parse an RRULE string into a dict of components."""
    if not rrule_str:
        return {}

    # Strip "RRULE:" prefix if present
    rule = rrule_str.strip()
    if rule.upper().startswith("RRULE:"):
        rule = rule[6:]

    parts = {}
    for segment in rule.split(";"):
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        parts[key.upper().strip()] = value.strip()

    return parts


def expand_rrule(
    rrule_str: str,
    event_start: datetime,
    event_end: Optional[datetime],
    range_start: datetime,
    range_end: datetime,
    max_occurrences: int = 200,
) -> list[dict]:
    """
    Expand an RRULE into concrete occurrences within a date range.

    Returns list of {"start_at": datetime, "end_at": datetime}
    """
    parts = parse_rrule(rrule_str)
    if not parts or "FREQ" not in parts:
        return []

    freq = parts["FREQ"].upper()
    interval = int(parts.get("INTERVAL", "1"))
    count = int(parts["COUNT"]) if "COUNT" in parts else None
    until = _parse_until(parts.get("UNTIL")) if "UNTIL" in parts else None
    byday = _parse_byday(parts.get("BYDAY", ""))

    # Event duration for computing end_at of each occurrence
    duration = (event_end - event_start) if event_end else timedelta(hours=1)

    occurrences = []
    current = event_start
    generated = 0

    # Safety limit
    max_iterations = max_occurrences * 10

    for _ in range(max_iterations):
        if count and generated >= count:
            break
        if until and current > until:
            break
        if current > range_end:
            break

        # Check if this occurrence falls within the requested range
        occ_end = current + duration
        if occ_end >= range_start and current <= range_end:
            # For WEEKLY with BYDAY, check day match
            if freq == "WEEKLY" and byday:
                if current.weekday() in byday:
                    occurrences.append({
                        "start_at": current.isoformat(),
                        "end_at": occ_end.isoformat(),
                    })
                    generated += 1
            else:
                occurrences.append({
                    "start_at": current.isoformat(),
                    "end_at": occ_end.isoformat(),
                })
                generated += 1
        elif current < range_start:
            generated += 1  # Count towards COUNT limit even if before range

        # Advance to next occurrence
        if freq == "DAILY":
            current += timedelta(days=interval)
        elif freq == "WEEKLY":
            if byday:
                # Advance to next matching day
                current += timedelta(days=1)
                safety = 0
                while current.weekday() not in byday and safety < 14:
                    current += timedelta(days=1)
                    safety += 1
                # After cycling through all BYDAY days in a week, skip to next interval
            else:
                current += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            month = current.month + interval
            year = current.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(current.day, _days_in_month(year, month))
            current = current.replace(year=year, month=month, day=day)
        elif freq == "YEARLY":
            try:
                current = current.replace(year=current.year + interval)
            except ValueError:
                # Feb 29 on non-leap year
                current = current.replace(
                    year=current.year + interval, month=2, day=28
                )
        else:
            break

        if len(occurrences) >= max_occurrences:
            break

    return occurrences


def rrule_to_human(rrule_str: str) -> str:
    """Convert an RRULE string to a human-readable description."""
    parts = parse_rrule(rrule_str)
    if not parts or "FREQ" not in parts:
        return ""

    freq = parts["FREQ"].upper()
    interval = int(parts.get("INTERVAL", "1"))
    count = parts.get("COUNT")
    until = parts.get("UNTIL")
    byday = parts.get("BYDAY", "")

    # Base frequency
    if freq == "DAILY":
        base = "Every day" if interval == 1 else f"Every {interval} days"
    elif freq == "WEEKLY":
        if interval == 1:
            base = "Every week"
        else:
            base = f"Every {interval} weeks"
        # Add day names
        if byday:
            day_codes = [d.strip() for d in byday.split(",")]
            day_names = [WEEKDAY_NAMES.get(d, d) for d in day_codes]
            if len(day_names) == 1:
                base = f"Every {day_names[0]}" if interval == 1 else base + f" on {day_names[0]}"
            else:
                base += f" on {', '.join(day_names[:-1])} and {day_names[-1]}"
    elif freq == "MONTHLY":
        base = "Every month" if interval == 1 else f"Every {interval} months"
    elif freq == "YEARLY":
        base = "Every year" if interval == 1 else f"Every {interval} years"
    else:
        return rrule_str

    # End condition
    suffix = ""
    if count:
        suffix = f", {count} times"
    elif until:
        try:
            until_dt = _parse_until(until)
            if until_dt:
                suffix = f", until {until_dt.strftime('%b %d, %Y')}"
        except Exception:
            pass

    return base + suffix


# --- Helpers ---

def _parse_until(until_str: str) -> Optional[datetime]:
    """Parse UNTIL value from RRULE."""
    if not until_str:
        return None
    try:
        # Format: YYYYMMDDTHHMMSSZ or YYYYMMDD
        clean = until_str.replace("Z", "").replace("-", "").replace(":", "")
        if "T" in clean:
            return datetime.strptime(clean, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return datetime.strptime(clean, "%Y%m%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _parse_byday(byday_str: str) -> list[int]:
    """Parse BYDAY into list of weekday integers (0=Monday)."""
    if not byday_str:
        return []
    days = []
    for d in byday_str.split(","):
        d = d.strip().upper()
        # Strip numeric prefix (e.g. "1MO" → "MO")
        code = "".join(c for c in d if c.isalpha())
        if code in WEEKDAY_MAP:
            days.append(WEEKDAY_MAP[code])
    return days


def _days_in_month(year: int, month: int) -> int:
    """Get number of days in a month."""
    if month == 12:
        return 31
    from calendar import monthrange
    return monthrange(year, month)[1]
