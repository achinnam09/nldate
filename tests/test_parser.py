"""Tests for nldate.parse()."""

from datetime import date

import pytest

from nldate import parse

# A fixed reference date so tests are deterministic.
# 2025-06-15 is a Sunday.
REF = date(2025, 6, 15)


# ---------------------------------------------------------------------------
# Keyword dates
# ---------------------------------------------------------------------------


def test_today() -> None:
    assert parse("today", today=REF) == REF


def test_tomorrow() -> None:
    assert parse("tomorrow", today=REF) == date(2025, 6, 16)


def test_yesterday() -> None:
    assert parse("yesterday", today=REF) == date(2025, 6, 14)


# ---------------------------------------------------------------------------
# Absolute dates in multiple formats
# ---------------------------------------------------------------------------


def test_absolute_long_form() -> None:
    assert parse("December 1, 2025", today=REF) == date(2025, 12, 1)


def test_absolute_with_ordinal() -> None:
    assert parse("December 1st, 2025", today=REF) == date(2025, 12, 1)


def test_absolute_iso() -> None:
    assert parse("2025-12-01", today=REF) == date(2025, 12, 1)


def test_absolute_slash_us() -> None:
    assert parse("12/1/2025", today=REF) == date(2025, 12, 1)


def test_absolute_abbreviated_month() -> None:
    assert parse("Dec 1 2025", today=REF) == date(2025, 12, 1)


# ---------------------------------------------------------------------------
# Relative offsets
# ---------------------------------------------------------------------------


def test_in_n_days() -> None:
    assert parse("in 3 days", today=REF) == date(2025, 6, 18)


def test_n_days_ago() -> None:
    assert parse("5 days ago", today=REF) == date(2025, 6, 10)


def test_in_two_weeks_word() -> None:
    assert parse("in two weeks", today=REF) == date(2025, 6, 29)


def test_n_months_from_now() -> None:
    assert parse("3 months from now", today=REF) == date(2025, 9, 15)


def test_n_years_ago() -> None:
    assert parse("1 year ago", today=REF) == date(2024, 6, 15)


# ---------------------------------------------------------------------------
# Weekday-relative
# ---------------------------------------------------------------------------


def test_next_tuesday() -> None:
    # REF is Sunday (2025-06-15); next Tuesday is 2 days later.
    assert parse("next Tuesday", today=REF) == date(2025, 6, 17)


def test_last_friday() -> None:
    # Last Friday before Sunday 2025-06-15 is 2025-06-13.
    assert parse("last Friday", today=REF) == date(2025, 6, 13)


def test_next_same_weekday_is_seven_days_out() -> None:
    # "next Sunday" when today is Sunday -> 7 days later, not today.
    assert parse("next Sunday", today=REF) == date(2025, 6, 22)


# ---------------------------------------------------------------------------
# Composite expressions (the trickiest)
# ---------------------------------------------------------------------------


def test_days_before_absolute() -> None:
    assert parse("5 days before December 1, 2025", today=REF) == date(2025, 11, 26)


def test_year_and_months_after_yesterday() -> None:
    # yesterday = 2025-06-14; + 1 year 2 months = 2026-08-14.
    assert parse("1 year and 2 months after yesterday", today=REF) == date(2026, 8, 14)


def test_weeks_after_next_monday() -> None:
    # REF Sunday; next Monday = 2025-06-16; + 3 weeks = 2025-07-07.
    assert parse("3 weeks after next Monday", today=REF) == date(2025, 7, 7)


def test_default_today_is_used() -> None:
    # When `today` is omitted, "today" must equal date.today().
    assert parse("today") == date.today()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_unparseable_raises() -> None:
    with pytest.raises(ValueError):
        parse("the day the music died", today=REF)
