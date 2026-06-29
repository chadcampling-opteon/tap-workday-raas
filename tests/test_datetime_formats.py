"""Tests for Workday datetime format helpers."""

from datetime import datetime, timedelta, timezone

from tap_workday_raas.datetime_formats import (
    format_workday_bookmark,
    format_workday_datetime,
)


def test_date_format() -> None:
    value = datetime(2026, 6, 29, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert format_workday_bookmark(value, "date") == "2026-06-29"


def test_isoformat_with_source_offset() -> None:
    value = datetime(2026, 6, 29, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert format_workday_bookmark(value, "datetime") == "2026-06-29T07:00:00.000-07:00"


def test_isoformat_utc_uses_z_suffix() -> None:
    value = datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert format_workday_datetime(value) == "2025-07-01T00:00:00.000Z"
