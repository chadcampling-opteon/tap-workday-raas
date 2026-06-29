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

from decimal import Decimal
from typing import Any

SINGER_DECIMAL_FORMAT = "singer.decimal"


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

    if schema.get("format") == SINGER_DECIMAL_FORMAT:
        return _coerce_singer_decimal(value)

    types = schema_type if isinstance(schema_type, list) else [schema_type]
    if "boolean" in types:
        return _coerce_boolean(value)

    return value


def coerce_record(record: dict, schema: dict) -> dict:
    """Coerce Workday record values to match the stream JSON schema."""
    return _walk_schema(record, schema)
