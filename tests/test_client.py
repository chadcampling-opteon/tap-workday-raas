"""Tests for URL building and state value formatting."""

from datetime import datetime, timedelta, timezone

from tap_workday_raas.client import (
    apply_format_json,
    build_report_url,
    format_state_value,
)


def test_apply_format_json_adds_param() -> None:
    url = "https://example.workday.com/report/MyReport?Posted_Date=01%2F01%2F2024"
    result = apply_format_json(url)
    assert "format=json" in result
    assert "format=xml" not in result
    assert "Posted_Date=01%2F01%2F2024" in result


def test_apply_format_json_replaces_existing_format() -> None:
    url = "https://example.workday.com/report/MyReport?format=csv&Other=1"
    result = apply_format_json(url)
    assert "format=json" in result
    assert "format=csv" not in result


def test_apply_format_json_does_not_double_encode() -> None:
    url = "https://example.workday.com/report/MyReport?Posted_Date=01%2F01%2F2024"
    once = apply_format_json(url)
    twice = apply_format_json(once)
    assert twice == once
    assert "%252F" not in twice


def test_format_state_value_uses_iso8601() -> None:
    value = datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert format_state_value(value) == "2025-07-01T00:00:00.000Z"


def test_format_state_value_date_format() -> None:
    value = datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert format_state_value(value, state_param_format="date") == "2024-06-01"


def test_build_report_url_encodes_workday_params() -> None:
    url = (
        "https://wd3-services1.myworkday.com/ccx/service/customreport2/tenant/user/"
        "SNOW_-_Journal_Lines?Year!WID=fc3da00533be01774727341ee900df1b"
    )
    result = build_report_url(
        url,
        state_param="Posted_Date",
        state_value=datetime(2026, 6, 29, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7))),
    )
    assert "Year%21WID=fc3da00533be01774727341ee900df1b" in result
    assert "Posted_Date=2026-06-29T07%3A00%3A00.000-07%3A00" in result
    assert "format=json" in result


def test_apply_format_json_encodes_special_characters_in_param_names() -> None:
    url = "https://example.workday.com/report/MyReport?Year!WID=abc"
    result = apply_format_json(url)
    assert "Year%21WID=abc" in result
    assert "format=json" in result


def test_apply_format_json_preserves_utc_offset_in_posted_date() -> None:
    url = (
        "https://example.workday.com/report/MyReport?"
        "Posted_Date=2025-07-01T00:00:00.000%2B00:00"
    )
    result = apply_format_json(url)
    assert "Posted_Date=2025-07-01T00%3A00%3A00.000%2B00%3A00" in result
    assert "%20" not in result
    assert "format=json" in result


def test_build_report_url_utc_offset_survives_format_json_round_trip() -> None:
    base = "https://example.workday.com/report/MyReport"
    built = build_report_url(
        base,
        state_param="Posted_Date",
        state_value=datetime(2025, 7, 1, tzinfo=timezone.utc),
    )
    result = apply_format_json(built)
    assert result == built
    assert "Posted_Date=2025-07-01T00%3A00%3A00.000Z" in result
    assert "%20" not in result
    assert "%252B" not in result


def test_format_state_value_numeric() -> None:
    assert format_state_value(1042) == "1042"
    assert format_state_value(3.5) == "3.5"


def test_format_state_value_string() -> None:
    assert format_state_value("abc-123") == "abc-123"


def test_build_report_url_replaces_existing_state_param() -> None:
    url = "https://example.workday.com/report/MyReport?Posted_Date=01%2F01%2F2020"
    result = build_report_url(
        url,
        state_param="Posted_Date",
        state_value="1042",
    )
    assert "Posted_Date=1042" in result
    assert "01%2F01%2F2020" not in result
