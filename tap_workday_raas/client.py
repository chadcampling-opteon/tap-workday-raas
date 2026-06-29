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

"""HTTP client helpers for Workday RaaS reports."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

import ijson
import requests

from tap_workday_raas.exceptions import (
    map_connection_error,
    map_http_error,
    raise_fatal,
)

from tap_workday_raas.datetime_formats import (
    BookmarkFormat,
    DEFAULT_BOOKMARK_FORMAT,
    format_workday_bookmark,
)

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 300.0


def resolve_request_timeout(config: dict[str, Any]) -> float | None:
    """Return HTTP timeout in seconds, or ``None`` to wait indefinitely."""
    if "request_timeout" in config:
        value = config["request_timeout"]
        return None if value is None else float(value)
    return DEFAULT_REQUEST_TIMEOUT


def _requests_timeout_kwargs(timeout: float | None) -> dict[str, float]:
    if timeout is None:
        return {}
    return {"timeout": timeout}

def _parse_query_string(query: str) -> dict[str, str]:
    """Decode a query string into raw parameter values.

    Uses ``unquote`` (not ``unquote_plus``) so a literal ``+`` in a value is
    never mistaken for a space.
    """
    if not query:
        return {}
    params: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        key, sep, value = part.partition("=")
        if not sep:
            params[unquote(key)] = ""
        else:
            params[unquote(key)] = unquote(value)
    return params


def _build_query_string(params: dict[str, str]) -> str:
    """Encode raw parameter values into a query string (once)."""
    return urlencode(params, quote_via=quote)


def _with_query_params(url: str, updates: dict[str, str | None]) -> str:
    """Return *url* with decoded query params merged and re-encoded once."""
    parts = urlsplit(url)
    params = _parse_query_string(parts.query)
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, _build_query_string(params), parts.fragment),
    )


def apply_format_json(report_url: str) -> str:
    """Ensure the report URL requests JSON output."""
    return _with_query_params(report_url, {"format": "json"})


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def format_state_value(
    value: Any,
    state_param_format: BookmarkFormat = DEFAULT_BOOKMARK_FORMAT,
) -> str:
    """Format a bookmark value for injection into a Workday report URL."""
    if value is None:
        msg = "Bookmark value cannot be None"
        raise ValueError(msg)

    parsed_dt = _parse_datetime(value)
    if parsed_dt is not None:
        return format_workday_bookmark(parsed_dt, state_param_format)

    if isinstance(value, bool):
        return str(value).lower()

    if isinstance(value, int | float):
        return str(value)

    return str(value)


def build_report_url(
    report_url: str,
    *,
    state_param: str | None = None,
    state_value: Any = None,
    state_param_format: BookmarkFormat = DEFAULT_BOOKMARK_FORMAT,
) -> str:
    """Build a report URL with format=json and optional state param injection."""
    url = apply_format_json(report_url)
    if not state_param or state_value is None:
        return url

    return _with_query_params(
        url,
        {state_param: format_state_value(state_value, state_param_format)},
    )


def stream_report(
    report_url: str,
    user: str,
    password: str,
    *,
    timeout: float | None = DEFAULT_REQUEST_TIMEOUT,
) -> Iterator[dict]:
    """Stream Report_Entry records from a Workday RaaS JSON report."""
    try:
        with requests.get(
            report_url,
            auth=(user, password),
            stream=True,
            **_requests_timeout_kwargs(timeout),
        ) as resp:
            resp.raise_for_status()
            # Decode Content-Encoding (e.g. gzip) on the socket stream. Without
            # this, ijson reads compressed bytes. iter_content() in the legacy
            # tap handled decompression automatically.
            resp.raw.decode_content = True
            record_count = 0
            for record in ijson.items(resp.raw, "Report_Entry.item"):
                record_count += 1
                yield record
            if record_count == 0:
                logger.info("Report returned zero records: %s", report_url)
    except requests.exceptions.HTTPError as exc:
        raise_fatal(map_http_error(exc, report_url))
    except requests.exceptions.ConnectionError as exc:
        raise_fatal(map_connection_error(exc, report_url))


def download_xsd(
    report_url: str,
    user: str,
    password: str,
    *,
    timeout: float | None = DEFAULT_REQUEST_TIMEOUT,
) -> str:
    """Download the XSD schema document for a Workday report."""
    base = report_url.split("?", maxsplit=1)[0]
    xsds_url = f"{base}?xsds"

    try:
        response = requests.get(
            xsds_url,
            auth=(user, password),
            **_requests_timeout_kwargs(timeout),
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise_fatal(map_http_error(exc, report_url, xsds_request=True))
    except requests.exceptions.ConnectionError as exc:
        raise_fatal(map_connection_error(exc, report_url))
    else:
        return response.text
