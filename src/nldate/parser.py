"""Natural-language date parser.

Strategy (in order of attempt):
  1. Normalize input (lowercase, strip ordinals, collapse whitespace).
  2. Check keyword dates: today / tomorrow / yesterday.
  3. Check "X <unit>s ago" / "in X <units>" / "X <units> from now".
  4. Check "next / last / this <weekday>".
  5. Check composite "X <units> before/after <anchor>" -- recurse on anchor.
  6. Fall back to dateutil.parser.parse() for absolute dates.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from dateutil import parser as du_parser
from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_NUMBER_WORDS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "a": 1,
    "an": 1,
}

_WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

_UNIT_PATTERN = r"(?:days?|weeks?|months?|years?)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_int(token: str) -> int:
    """Convert '5' or 'five' to an int. Raises ValueError if neither."""
    token = token.strip().lower()
    if token in _NUMBER_WORDS:
        return _NUMBER_WORDS[token]
    return int(token)


def _delta(amount: int, unit: str) -> relativedelta:
    """Build a relativedelta from an amount and a unit word."""
    unit = unit.lower().rstrip("s")
    if unit == "day":
        return relativedelta(days=amount)
    if unit == "week":
        return relativedelta(weeks=amount)
    if unit == "month":
        return relativedelta(months=amount)
    if unit == "year":
        return relativedelta(years=amount)
    raise ValueError(f"Unknown unit: {unit}")


def _normalize(s: str) -> str:
    """Lowercase, strip ordinal suffixes (1st->1), collapse whitespace."""
    s = s.strip().lower()
    # Strip ordinal suffixes attached to digits: 1st, 2nd, 23rd, 4th -> 1, 2, 23, 4
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s)
    # Collapse internal whitespace.
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_leading_filler(s: str) -> str:
    """Remove leading 'on ' or 'the ' that can appear in anchors."""
    s = re.sub(r"^(on|the)\s+", "", s)
    return s


# ---------------------------------------------------------------------------
# Pattern handlers
# ---------------------------------------------------------------------------


def _try_keyword(s: str, today: date) -> date | None:
    if s == "today" or s == "now":
        return today
    if s == "tomorrow":
        return today + relativedelta(days=1)
    if s == "yesterday":
        return today + relativedelta(days=-1)
    return None


def _try_relative_offset(s: str, today: date) -> date | None:
    """Handle 'in N <units>', 'N <units> from now', 'N <units> ago'."""
    # "in N <units>" or "in N <units> from now"
    m = re.fullmatch(
        rf"in\s+(\w+)\s+({_UNIT_PATTERN})(?:\s+from\s+now)?",
        s,
    )
    if m:
        n = _to_int(m.group(1))
        return today + _delta(n, m.group(2))

    # "N <units> from now" / "N <units> from today"
    m = re.fullmatch(
        rf"(\w+)\s+({_UNIT_PATTERN})\s+from\s+(?:now|today)",
        s,
    )
    if m:
        n = _to_int(m.group(1))
        return today + _delta(n, m.group(2))

    # "N <units> ago"
    m = re.fullmatch(rf"(\w+)\s+({_UNIT_PATTERN})\s+ago", s)
    if m:
        n = _to_int(m.group(1))
        return today - _delta(n, m.group(2))

    return None


def _try_weekday(s: str, today: date) -> date | None:
    """Handle 'next Tuesday', 'last Friday', 'this Monday', bare 'Tuesday'."""
    m = re.fullmatch(r"(next|last|this)\s+(\w+)", s)
    if m:
        modifier, day_word = m.group(1), m.group(2)
        if day_word not in _WEEKDAYS:
            return None
        target = _WEEKDAYS[day_word]
        current = today.weekday()
        if modifier == "next":
            # Convention: "next X" is always 1..7 days forward.
            # If today is X, "next X" means 7 days from now.
            diff = (target - current) % 7
            if diff == 0:
                diff = 7
            return today + relativedelta(days=diff)
        if modifier == "last":
            diff = (current - target) % 7
            if diff == 0:
                diff = 7
            return today - relativedelta(days=diff)
        if modifier == "this":
            # "this X": the X in the current week. If today is X, return today.
            diff = (target - current) % 7
            return today + relativedelta(days=diff)

    # Bare weekday name (e.g., "Tuesday") -> treat as the nearest upcoming one.
    if s in _WEEKDAYS:
        target = _WEEKDAYS[s]
        current = today.weekday()
        diff = (target - current) % 7
        if diff == 0:
            diff = 7
        return today + relativedelta(days=diff)

    return None


def _try_composite(s: str, today: date) -> date | None:
    """Handle 'N <units> [and M <units>] before/after <anchor>'.

    Examples:
        '5 days before December 1, 2025'
        '1 year and 2 months after yesterday'
        '3 weeks after next monday'
    """
    # Match an optional second amount/unit: "1 year and 2 months"
    pattern = re.fullmatch(
        rf"(\w+)\s+({_UNIT_PATTERN})"
        rf"(?:\s+and\s+(\w+)\s+({_UNIT_PATTERN}))?"
        rf"\s+(before|after|from|prior\s+to)\s+(.+)",
        s,
    )
    if not pattern:
        return None

    n1 = _to_int(pattern.group(1))
    u1 = pattern.group(2)
    n2_raw = pattern.group(3)
    u2 = pattern.group(4)
    direction = pattern.group(5)
    anchor_str = pattern.group(6)

    total = _delta(n1, u1)
    if n2_raw is not None and u2 is not None:
        total += _delta(_to_int(n2_raw), u2)

    # Recurse: the anchor itself is a date expression.
    anchor = parse(_strip_leading_filler(anchor_str), today)

    if direction in ("after", "from"):
        return anchor + total
    # "before" or "prior to"
    return anchor - total


def _try_absolute(s: str) -> date | None:
    """Fall back to dateutil for absolute date strings."""
    try:
        # dayfirst=False matches US convention (12/1/2025 = Dec 1)
        parsed: datetime = du_parser.parse(s, dayfirst=False, fuzzy=False)
    except (ValueError, OverflowError):
        return None
    return parsed.date()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(s: str, today: date | None = None) -> date:
    """Parse a natural-language date string into a datetime.date.

    Args:
        s: The natural-language date string.
        today: Reference date for relative expressions. Defaults to
            date.today().

    Returns:
        A datetime.date object.

    Raises:
        ValueError: If the input cannot be parsed.
    """
    if today is None:
        today = date.today()

    normalized = _normalize(s)
    if not normalized:
        raise ValueError("Empty date string")

    for handler in (
        _try_keyword,
        _try_relative_offset,
        _try_weekday,
        _try_composite,
    ):
        result = handler(normalized, today)
        if result is not None:
            return result

    absolute = _try_absolute(normalized)
    if absolute is not None:
        return absolute

    raise ValueError(f"Could not parse date string: {s!r}")
