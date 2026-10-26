"""Tests for report window paging."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from singer_sdk.exceptions import ConfigValidationError

from tap_workday_raas.paging import (
    DatePaging,
    NumberPaging,
    PageWindow,
    next_page_window,
    paging_from_report,
)

UTC = timezone.utc
NOW = datetime(2024, 1, 20, tzinfo=UTC)


def _windows(start: object, paging: DatePaging | NumberPaging) -> list[PageWindow]:
    windows: list[PageWindow] = []
    cursor: object = start
    while True:
        window = next_page_window(cursor, paging, now=NOW)
        if window is None:
            break
        windows.append(window)
        if window.is_last or window.stop_on_empty:
            break
        cursor = window.end
    return windows


def test_month_step_clamps_only_when_the_day_is_missing() -> None:
    january = paging_from_report(
        {
            "report_name": "journal",
            "state_param": "Date_From",
            "replication_key": "Posted_Date",
            "start_date": "2024-01-31T00:00:00Z",
            "paging": {"param": "Date_To", "size": "P1M", "until": "2024-04-01T00:00:00Z"},
        },
    )
    assert isinstance(january, DatePaging)
    windows = _windows(datetime(2024, 1, 31, tzinfo=UTC), january)
    assert windows[0].end == datetime(2024, 2, 29, tzinfo=UTC)

    june = paging_from_report(
        {
            "report_name": "journal",
            "state_param": "Date_From",
            "replication_key": "Posted_Date",
            "start_date": "2022-06-28T00:00:00Z",
            "paging": {"param": "Date_To", "size": "P1M", "until": "2022-08-28T00:00:00Z"},
        },
    )
    assert isinstance(june, DatePaging)
    june_windows = _windows(datetime(2022, 6, 28, tzinfo=UTC), june)
    assert june_windows[0].end == datetime(2022, 7, 28, tzinfo=UTC)
    assert june_windows[1].end == datetime(2022, 8, 28, tzinfo=UTC)
    assert june_windows[1].is_last is True


def test_non_leap_january_clamps_to_february_28() -> None:
    paging = paging_from_report(
        {
            "report_name": "journal",
            "state_param": "Date_From",
            "replication_key": "Posted_Date",
            "start_date": "2023-01-31T00:00:00Z",
            "paging": {"param": "Date_To", "size": "P1M", "until": "2023-03-01T00:00:00Z"},
        },
    )
    assert isinstance(paging, DatePaging)
    windows = _windows(datetime(2023, 1, 31, tzinfo=UTC), paging)
    assert windows[0].end == datetime(2023, 2, 28, tzinfo=UTC)


def test_date_windows_stop_at_until() -> None:
    paging = paging_from_report(
        {
            "report_name": "journal",
            "state_param": "Date_From",
            "replication_key": "Posted_Date",
            "start_date": "2022-06-28T00:00:00Z",
            "paging": {"param": "Date_To", "size": "P14D", "until": "2022-07-20T00:00:00Z"},
        },
    )
    assert isinstance(paging, DatePaging)
    windows = _windows(datetime(2022, 6, 28, tzinfo=UTC), paging)
    assert [(window.start, window.end, window.is_last) for window in windows] == [
        (
            datetime(2022, 6, 28, tzinfo=UTC),
            datetime(2022, 7, 12, tzinfo=UTC),
            False,
        ),
        (
            datetime(2022, 7, 12, tzinfo=UTC),
            datetime(2022, 7, 20, tzinfo=UTC),
            True,
        ),
    ]
    assert all(window.stop_on_empty is False for window in windows)


def test_integer_size_is_days_for_a_datetime_bookmark() -> None:
    paging = paging_from_report(
        {
            "report_name": "journal",
            "state_param": "Date_From",
            "replication_key": "Posted_Date",
            "start_date": "2024-01-01T00:00:00Z",
            "paging": {"param": "Date_To", "size": 7},
        },
    )
    assert isinstance(paging, DatePaging)
    windows = _windows(datetime(2024, 1, 1, tzinfo=UTC), paging)
    assert windows[0].end == datetime(2024, 1, 8, tzinfo=UTC)
    assert windows[-1].end == NOW
    assert windows[-1].is_last is True


def test_number_windows_stop_at_until() -> None:
    paging = paging_from_report(
        {
            "report_name": "entries",
            "state_param": "From_ID",
            "replication_key": "Entry_ID",
            "start_value": "0",
            "paging": {"param": "To_ID", "size": 1000, "until": 2500},
        },
    )
    assert isinstance(paging, NumberPaging)
    windows = _windows(Decimal(0), paging)
    assert [(window.start, window.end, window.is_last) for window in windows] == [
        (Decimal(0), Decimal(1000), False),
        (Decimal(1000), Decimal(2000), False),
        (Decimal(2000), Decimal(2500), True),
    ]


def test_open_numeric_window_stops_on_empty_page() -> None:
    paging = paging_from_report(
        {
            "report_name": "entries",
            "state_param": "From_ID",
            "replication_key": "Entry_ID",
            "start_value": "0",
            "paging": {"param": "To_ID", "size": 1000, "until": ""},
        },
    )
    assert isinstance(paging, NumberPaging)
    windows = _windows("0", paging)
    assert len(windows) == 1
    assert windows[0].start == Decimal(0)
    assert windows[0].end == Decimal(1000)
    assert windows[0].stop_on_empty is True
    assert windows[0].is_last is False


def test_blank_until_is_omitted() -> None:
    paging = paging_from_report(
        {
            "report_name": "journal",
            "state_param": "Date_From",
            "replication_key": "Posted_Date",
            "start_date": "2024-01-01T00:00:00Z",
            "paging": {"param": "Date_To", "size": "P1D", "until": "  "},
        },
    )
    assert isinstance(paging, DatePaging)
    assert paging.until is None


@pytest.mark.parametrize(
    ("report", "match"),
    [
        (
            {
                "report_name": "missing_incremental",
                "report_url": "https://example.com/report",
                "paging": {"param": "Date_To", "size": "P1D"},
            },
            "state_param and replication_key",
        ),
        (
            {
                "report_name": "same_param",
                "state_param": "Date_From",
                "replication_key": "Posted_Date",
                "start_date": "2024-01-01T00:00:00Z",
                "paging": {"param": "Date_From", "size": "P1D"},
            },
            "must differ from state_param",
        ),
        (
            {
                "report_name": "zero_days",
                "state_param": "Date_From",
                "replication_key": "Posted_Date",
                "start_date": "2024-01-01T00:00:00Z",
                "paging": {"param": "Date_To", "size": 0},
            },
            "positive integer",
        ),
        (
            {
                "report_name": "duration_on_number",
                "state_param": "From_ID",
                "replication_key": "Entry_ID",
                "start_value": "0",
                "paging": {"param": "To_ID", "size": "P14D"},
            },
            "duration paging.size is only valid for a datetime bookmark",
        ),
        (
            {
                "report_name": "no_start",
                "state_param": "Date_From",
                "replication_key": "Posted_Date",
                "paging": {"param": "Date_To", "size": "P1D"},
            },
            "start_date or start_value",
        ),
    ],
)
def test_invalid_paging_config(report: dict, match: str) -> None:
    with pytest.raises(ConfigValidationError, match=match):
        paging_from_report(report)
