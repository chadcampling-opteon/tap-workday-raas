"""Tests for record coercion."""

from decimal import Decimal

from tap_workday_raas.transform import (
    _coerce_boolean,
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
