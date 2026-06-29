# Copyright (c) 2026 Opteon Solutions
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Workday bookmark formatting for URL state parameters.

See Workday's date/time handling documentation:
https://developer.workday.com/documentation/dan1370797984883/ConceptWorkdayWebServiceAPIDateTimeandTimeZoneHandling
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

BookmarkFormat = Literal["date", "datetime"]

BOOKMARK_FORMATS: tuple[BookmarkFormat, ...] = ("date", "datetime")

DEFAULT_BOOKMARK_FORMAT: BookmarkFormat = "datetime"


def format_workday_datetime(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with millisecond precision.

    UTC values use the ``Z`` suffix instead of ``+00:00``.
    """
    formatted = dt.isoformat(timespec="milliseconds")
    if formatted.endswith("+00:00"):
        return f"{formatted[:-6]}Z"
    return formatted


def format_workday_bookmark(dt: datetime, fmt: BookmarkFormat = DEFAULT_BOOKMARK_FORMAT) -> str:
    """Format a datetime bookmark for a Workday report URL."""
    if fmt == "date":
        return dt.strftime("%Y-%m-%d")
    return format_workday_datetime(dt)
