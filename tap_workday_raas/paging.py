# Copyright (c) 2026 Opteon Solutions
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Window math for optional Workday RaaS report paging."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from singer_sdk.exceptions import ConfigValidationError

from tap_workday_raas.client import parse_datetime_value

_DURATION_RE = re.compile(
    r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?"
    r"(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$",
)


@dataclass(frozen=True)
class Duration:
    """ISO-8601 duration used as a datetime page size."""

    years: int = 0
    months: int = 0
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: float = 0

    def is_zero(self) -> bool:
        """Return True when every component is zero."""
        return (
            self.years == self.months == self.weeks == self.days == 0
            and self.hours == self.minutes == 0
            and self.seconds == 0
        )


@dataclass(frozen=True)
class PageWindow:
    """One inclusive request window.

    ``stop_on_empty`` is set for an open-ended numeric bookmark. The caller
    stops after an empty page instead of treating the window end as a bookmark.
    """

    start: datetime | Decimal
    end: datetime | Decimal
    is_last: bool
    stop_on_empty: bool


@dataclass(frozen=True)
class DatePaging:
    """Paging for a datetime bookmark."""

    report_name: str
    param: str
    step: timedelta | Duration
    until: datetime | None


@dataclass(frozen=True)
class NumberPaging:
    """Paging for a numeric bookmark."""

    report_name: str
    param: str
    step: Decimal
    until: Decimal | None


Paging = DatePaging | NumberPaging


def paging_from_report(report: Mapping[str, Any]) -> Paging | None:
    """Return paging settings for a report, or None when paging is unset."""
    raw = report.get("paging")
    if raw is None:
        return None

    report_name = str(report.get("report_name") or "report")
    if not isinstance(raw, Mapping):
        raise _invalid(report_name, "paging must be an object with param, size, and optional until")

    if not report.get("state_param") or not report.get("replication_key"):
        raise _invalid(report_name, "paging requires state_param and replication_key")

    param = raw.get("param")
    if not isinstance(param, str) or not param.strip():
        raise _invalid(report_name, "paging.param is required")
    param = param.strip()
    if param == report.get("state_param"):
        raise _invalid(report_name, "paging.param must differ from state_param")

    if "size" not in raw or raw.get("size") is None:
        raise _invalid(report_name, "paging.size is required")

    bookmark = _initial_bookmark(report, report_name)
    until = _blank_to_none(raw.get("until"))
    if _is_datetime_bookmark(bookmark):
        return DatePaging(
            report_name=report_name,
            param=param,
            step=_date_step(raw.get("size"), report_name),
            until=None if until is None else _require_datetime(until, report_name, "paging.until"),
        )

    if _is_number(bookmark):
        return NumberPaging(
            report_name=report_name,
            param=param,
            step=_number_step(raw.get("size"), report_name),
            until=None if until is None else _require_number(until, report_name, "paging.until"),
        )

    raise _invalid(
        report_name,
        "paging requires a datetime bookmark (start_date) or a numeric bookmark (start_value)",
    )


def next_page_window(start: Any, paging: Paging, *, now: datetime) -> PageWindow | None:  # noqa: ANN401
    """Return the next window starting at ``start``, or None when paging is finished."""
    if isinstance(paging, DatePaging):
        return _next_date_window(start, paging, now=now)
    return _next_number_window(start, paging)


def _next_date_window(start: Any, paging: DatePaging, *, now: datetime) -> PageWindow | None:  # noqa: ANN401
    start_dt = _require_datetime(start, paging.report_name, "bookmark")
    ceiling = _aware(now) if paging.until is None else _aware(paging.until)
    if start_dt >= ceiling:
        return None

    end = _add_step(start_dt, paging.step)
    is_last = end >= ceiling
    if is_last:
        end = ceiling
    if end <= start_dt:
        raise _invalid(paging.report_name, "paging.size must move the window forward")
    return PageWindow(start=start_dt, end=end, is_last=is_last, stop_on_empty=False)


def _next_number_window(start: Any, paging: NumberPaging) -> PageWindow | None:  # noqa: ANN401
    start_value = _require_number(start, paging.report_name, "bookmark")
    if paging.until is not None and start_value >= paging.until:
        return None

    end = start_value + paging.step
    is_last = paging.until is not None and end >= paging.until
    if is_last and paging.until is not None:
        end = paging.until
    if end <= start_value:
        raise _invalid(paging.report_name, "paging.size must move the window forward")
    return PageWindow(
        start=start_value,
        end=end,
        is_last=is_last,
        stop_on_empty=paging.until is None,
    )


def _initial_bookmark(report: Mapping[str, Any], report_name: str) -> Any:  # noqa: ANN401
    if report.get("start_value") is not None:
        return report["start_value"]
    if report.get("start_date") is not None:
        return report["start_date"]
    raise _invalid(report_name, "paging requires start_date or start_value")


def _blank_to_none(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _is_datetime_bookmark(value: Any) -> bool:  # noqa: ANN401
    return parse_datetime_value(value) is not None


def _is_number(value: Any) -> bool:  # noqa: ANN401
    if isinstance(value, bool | datetime):
        return False
    if isinstance(value, int | float | Decimal):
        return True
    if isinstance(value, str):
        try:
            Decimal(value.strip())
        except InvalidOperation:
            return False
        return bool(value.strip())
    return False


def _date_step(size: Any, report_name: str) -> timedelta | Duration:  # noqa: ANN401
    if isinstance(size, bool):
        raise _invalid(report_name, "paging.size must be a duration or a positive number of days")

    if isinstance(size, int | float):
        return timedelta(days=_positive_day_count(size, report_name))

    if isinstance(size, str):
        text = size.strip()
        if not text:
            raise _invalid(report_name, "paging.size is required")
        if text[0] in {"P", "p"}:
            try:
                duration = _parse_duration(text)
            except ValueError:
                raise _invalid(
                    report_name,
                    "paging.size must be an ISO-8601 duration such as P14D or P1M, "
                    "or a positive number of days",
                ) from None
            if duration.is_zero():
                raise _invalid(report_name, "paging.size must move the window forward")
            return duration
        try:
            return timedelta(days=_positive_day_count(Decimal(text), report_name))
        except InvalidOperation:
            raise _invalid(
                report_name,
                "paging.size must be an ISO-8601 duration such as P14D or P1M, "
                "or a positive number of days",
            ) from None

    raise _invalid(report_name, "paging.size must be a duration or a positive number of days")


def _positive_day_count(size: float | Decimal, report_name: str) -> int:
    number = Decimal(str(size))
    if number != number.to_integral_value() or number <= 0:
        raise _invalid(report_name, "paging.size in days must be a positive integer")
    return int(number)


def _number_step(size: Any, report_name: str) -> Decimal:  # noqa: ANN401
    if isinstance(size, str) and size.strip()[:1] in {"P", "p"}:
        raise _invalid(report_name, "a duration paging.size is only valid for a datetime bookmark")
    try:
        step = _require_number(size, report_name, "paging.size")
    except ConfigValidationError:
        raise _invalid(
            report_name,
            "paging.size must be a positive number for a numeric bookmark",
        ) from None
    if step <= 0:
        raise _invalid(report_name, "paging.size must be a positive number for a numeric bookmark")
    return step


def _parse_duration(text: str) -> Duration:
    match = _DURATION_RE.fullmatch(text.upper())
    if match is None or not any(group is not None for group in match.groups()):
        msg = f"Invalid ISO-8601 duration: {text}"
        raise ValueError(msg)

    years, months, weeks, days, hours, minutes, seconds = match.groups()
    return Duration(
        years=int(years or 0),
        months=int(months or 0),
        weeks=int(weeks or 0),
        days=int(days or 0),
        hours=int(hours or 0),
        minutes=int(minutes or 0),
        seconds=float(seconds or 0),
    )


def _add_step(start: datetime, step: timedelta | Duration) -> datetime:
    if isinstance(step, timedelta):
        return start + step
    shifted = _shift_months(start, step.years * 12 + step.months)
    return shifted + timedelta(
        weeks=step.weeks,
        days=step.days,
        hours=step.hours,
        minutes=step.minutes,
        seconds=step.seconds,
    )


def _shift_months(start: datetime, months: int) -> datetime:
    """Add calendar months, clamping the day when it does not exist."""
    if months == 0:
        return start
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def _require_datetime(value: Any, report_name: str, label: str) -> datetime:  # noqa: ANN401
    parsed = parse_datetime_value(value)
    if parsed is None:
        raise _invalid(report_name, f"{label} must be a date or datetime")
    return _aware(parsed)


def _require_number(value: Any, report_name: str, label: str) -> Decimal:  # noqa: ANN401
    if isinstance(value, bool) or not _is_number(value):
        raise _invalid(report_name, f"{label} must be a number")
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        raise _invalid(report_name, f"{label} must be a number") from None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _invalid(report_name: str, detail: str) -> ConfigValidationError:
    msg = f"Report '{report_name}' paging config is invalid: {detail}"
    return ConfigValidationError(msg)
