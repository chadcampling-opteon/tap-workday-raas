# Copyright (c) 2026 Opteon Solutions
# Based on tap-workday-raas — Copyright (c) Stitch
#   https://github.com/singer-io/tap-workday-raas
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Record transformation helpers for Workday RaaS."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

SINGER_DECIMAL_FORMAT = "singer.decimal"
DATE_FORMAT = "date"
DATE_TIME_FORMAT = "date-time"


def _coerce_boolean(value: Any) -> Any:
    if isinstance(value, str) and value.lower() in ("false", "0"):
        return False
    if isinstance(value, str) and value.lower() in ("true", "1"):
        return True
    if isinstance(value, str):
        try:
            return bool(value)
        except (TypeError, ValueError):
            return None
    return value


def _coerce_singer_decimal(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    return str(value)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _coerce_datetime_to_utc(value: Any) -> str | None:
    """Normalize date-time values to UTC with a ``Z`` suffix.

    Matches the legacy singer-python Transformer behaviour used by the
    original tap: parse the Workday offset, convert to UTC, emit
    ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.
    """
    if value is None or value == "":
        return None

    parsed = _parse_datetime(value)
    if parsed is None:
        return None

    if parsed.tzinfo is None:
        utc_dt = parsed.replace(tzinfo=timezone.utc)
    else:
        utc_dt = parsed.astimezone(timezone.utc)

    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _coerce_date(value: Any) -> str | None:
    """Normalize calendar dates to ``YYYY-MM-DD`` (no timezone)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        # Workday may occasionally include a time; keep the calendar day.
        return value[:10] if len(value) >= 10 else value
    return str(value)


def _walk_schema(value: Any, schema: dict) -> Any:
    if value is None:
        return None

    schema_type = schema.get("type")
    if schema_type == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        return {
            key: _walk_schema(val, properties[key])
            for key, val in value.items()
            if key in properties
        }

    if schema_type == "array" and isinstance(value, list):
        items = schema.get("items", {})
        return [_walk_schema(item, items) for item in value]

    fmt = schema.get("format")
    if fmt == SINGER_DECIMAL_FORMAT:
        return _coerce_singer_decimal(value)
    if fmt == DATE_TIME_FORMAT:
        return _coerce_datetime_to_utc(value)
    if fmt == DATE_FORMAT:
        return _coerce_date(value)

    types = schema_type if isinstance(schema_type, list) else [schema_type]
    if "boolean" in types:
        return _coerce_boolean(value)

    return value


def coerce_record(record: dict, schema: dict) -> dict:
    """Coerce Workday record values to match the stream JSON schema."""
    return _walk_schema(record, schema)
