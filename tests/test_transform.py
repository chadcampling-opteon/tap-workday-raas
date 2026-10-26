"""Tests for record coercion."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from tap_workday_raas.transform import (
    _coerce_boolean,
    _coerce_date,
    _coerce_datetime_to_utc,
    _coerce_singer_decimal,
    coerce_record,
)


def test_coerce_boolean_false_values() -> None:
    assert _coerce_boolean("0") is False
    assert _coerce_boolean("False") is False
    assert _coerce_boolean("false") is False


def test_coerce_boolean_true_values() -> None:
    assert _coerce_boolean("1") is True
    assert _coerce_boolean("True") is True
    assert _coerce_boolean("true") is True


def test_coerce_singer_decimal_from_decimal() -> None:
    assert _coerce_singer_decimal(Decimal("1234.56")) == "1234.56"
    assert _coerce_singer_decimal(Decimal("92.123498765432")) == "92.123498765432"


def test_coerce_singer_decimal_from_string() -> None:
    assert _coerce_singer_decimal("9007199254740993.00") == "9007199254740993.00"


def test_coerce_singer_decimal_from_int() -> None:
    assert _coerce_singer_decimal(42) == "42"


def test_coerce_datetime_to_utc_from_offset() -> None:
    assert (
        _coerce_datetime_to_utc("2026-06-29T07:00:00.000-07:00")
        == "2026-06-29T14:00:00.000000Z"
    )


def test_coerce_datetime_to_utc_from_z() -> None:
    assert _coerce_datetime_to_utc("2025-07-01T00:00:00.000Z") == "2025-07-01T00:00:00.000000Z"


def test_coerce_datetime_to_utc_naive_assumes_utc() -> None:
    assert _coerce_datetime_to_utc("2025-07-01T12:30:00") == "2025-07-01T12:30:00.000000Z"


def test_coerce_datetime_to_utc_from_datetime_object() -> None:
    value = datetime(2026, 6, 29, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    assert _coerce_datetime_to_utc(value) == "2026-06-29T14:00:00.000000Z"


def test_coerce_date_from_string() -> None:
    assert _coerce_date("2024-01-15") == "2024-01-15"
    assert _coerce_date("2024-01-15T07:00:00.000-07:00") == "2024-01-15"


def test_coerce_date_from_date_object() -> None:
    assert _coerce_date(date(2024, 1, 15)) == "2024-01-15"


def test_coerce_record_booleans_in_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "active": {"type": ["boolean", "null"]},
            "name": {"type": ["string", "null"]},
        },
    }
    record = {"active": "0", "name": "test"}
    result = coerce_record(record, schema)
    assert result == {"active": False, "name": "test"}


def test_coerce_record_singer_decimals_in_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "amount": {"type": ["string", "null"], "format": "singer.decimal"},
            "name": {"type": ["string", "null"]},
        },
    }
    record = {"amount": Decimal("123456789012.34"), "name": "line"}
    result = coerce_record(record, schema)
    assert result == {"amount": "123456789012.34", "name": "line"}


def test_coerce_record_singer_decimals_in_nested_object() -> None:
    schema = {
        "type": "object",
        "properties": {
            "details": {
                "type": "object",
                "properties": {
                    "rate": {"type": ["string", "null"], "format": "singer.decimal"},
                },
            },
        },
    }
    record = {"details": {"rate": Decimal("0.125")}}
    result = coerce_record(record, schema)
    assert result == {"details": {"rate": "0.125"}}


def test_coerce_record_dates_and_datetimes() -> None:
    schema = {
        "type": "object",
        "properties": {
            "hire_date": {"type": ["string", "null"], "format": "date"},
            "posted_at": {"type": ["string", "null"], "format": "date-time"},
        },
    }
    record = {
        "hire_date": "2024-01-15",
        "posted_at": "2026-06-29T07:00:00.000-07:00",
    }
    result = coerce_record(record, schema)
    assert result == {
        "hire_date": "2024-01-15",
        "posted_at": "2026-06-29T14:00:00.000000Z",
    }
