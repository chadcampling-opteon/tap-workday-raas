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
import os
import tempfile
import threading
import time
from collections.abc import Generator, Iterator, Mapping
from contextlib import suppress
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

import ijson  # type: ignore[import-untyped]
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
DOWNLOAD_CHUNK_SIZE = 65_536
READ_CHUNK_SIZE = 65_536
DOWNLOAD_POLL_INTERVAL = 0.05
REPORT_ENTRY_KEY = b"Report_Entry"
REPORT_ENTRY_PREFIX = "Report_Entry.item"


def _ijson_backend() -> Any:
    """Return the fastest available ijson push-parser backend."""
    try:
        import ijson.backends.yajl2_c as backend  # type: ignore[import-untyped]
    except ImportError:
        import ijson.backends.python as backend  # type: ignore[import-untyped]
    return backend


def _raise_download_error(exc: BaseException, report_url: str) -> None:
    """Re-raise a background download failure with Workday error mapping."""
    if isinstance(exc, requests.exceptions.HTTPError):
        raise_fatal(map_http_error(exc, report_url))
    if isinstance(exc, requests.exceptions.ConnectionError):
        raise_fatal(map_connection_error(exc, report_url))
    raise exc


def resolve_request_timeout(config: Mapping[str, Any]) -> float | None:
    """Return HTTP timeout in seconds, or ``None`` to wait indefinitely."""
    if "request_timeout" in config:
        value = config["request_timeout"]
        return None if value is None else float(value)
    return DEFAULT_REQUEST_TIMEOUT


def _parse_query_string(query: str) -> dict[str, str]:
    """Decode a query string into raw parameter values.

    Splits on both ``&`` and ``;`` — Workday RaaS URLs often use semicolon as
    the parameter separator (CGI-style). The legacy tap preserved these by
    only rewriting the query with ``split("&")`` / ``"&".join(...)``, so a
    semicolon-separated prompt list was left intact; re-encoding without
    treating ``;`` as a separator collapses those prompts into one value.

    Uses ``unquote`` (not ``unquote_plus``) so a literal ``+`` in a value is
    never mistaken for a space.
    """
    if not query:
        return {}
    params: dict[str, str] = {}
    # Split on & or ; before decoding so %3B / %26 in values stay intact.
    for part in query.replace(";", "&").split("&"):
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


def _download_report_to_file(
    report_url: str,
    user: str,
    password: str,
    path: str,
    *,
    timeout: float | None,
    download_done: threading.Event,
    download_error: list[BaseException],
    stop_event: threading.Event,
) -> None:
    """Drain the HTTP response to *path* so the socket is not blocked by parsing."""
    try:
        with requests.get(
            report_url,
            auth=(user, password),
            stream=True,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            with open(path, "wb") as outfile:
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if stop_event.is_set():
                        break
                    if chunk:
                        outfile.write(chunk)
    except BaseException as exc:
        download_error.append(exc)
    finally:
        download_done.set()


def _close_parse_coroutine(
    coro: Any,
    *,
    download_error: list[BaseException],
    parse_complete: bool,
) -> None:
    """Close the ijson push coroutine, surfacing truncated JSON unless expected."""
    if download_error or not parse_complete:
        with suppress(Exception):
            coro.close()
    else:
        coro.close()


def _iter_records_from_file(
    path: str,
    *,
    download_done: threading.Event,
    download_error: list[BaseException],
    stop_event: threading.Event,
    report_url: str,
) -> Iterator[dict]:
    """Parse records from a report file while it may still be growing."""
    backend = _ijson_backend()
    records = ijson.sendable_list()
    coro = backend.items_coro(records, REPORT_ENTRY_PREFIX)
    found_key = False
    parse_complete = False

    try:
        with open(path, "rb") as infile:
            while True:
                if stop_event.is_set():
                    break

                if download_error:
                    _raise_download_error(download_error[0], report_url)

                chunk = infile.read(READ_CHUNK_SIZE)
                if chunk:
                    if REPORT_ENTRY_KEY in chunk:
                        found_key = True
                    coro.send(chunk)
                    yield from records
                    del records[:]
                    continue

                if download_done.is_set() and infile.tell() >= os.path.getsize(path):
                    parse_complete = True
                    break
                time.sleep(DOWNLOAD_POLL_INTERVAL)
    finally:
        stop_event.set()
        _close_parse_coroutine(
            coro,
            download_error=download_error,
            parse_complete=parse_complete,
        )

    if parse_complete and not found_key:
        logger.info("Report returned zero records: %s", report_url)


def stream_report(
    report_url: str,
    user: str,
    password: str,
    *,
    timeout: float | None = DEFAULT_REQUEST_TIMEOUT,
) -> Generator[dict, None, None]:
    """Stream Report_Entry records from a Workday RaaS JSON report.

    The HTTP response is drained to a temporary file on disk in a background
    thread while records are parsed and yielded from that file. This decouples
    socket reads from Singer emission so a slow target cannot stall the
    Workday connection and cause mid-stream disconnects.
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="tap-workday-raas-")
    os.close(fd)

    download_done = threading.Event()
    stop_event = threading.Event()
    download_error: list[BaseException] = []
    downloader = threading.Thread(
        target=_download_report_to_file,
        args=(report_url, user, password, path),
        kwargs={
            "timeout": timeout,
            "download_done": download_done,
            "download_error": download_error,
            "stop_event": stop_event,
        },
        name="workday-report-download",
        daemon=True,
    )

    try:
        downloader.start()
        yield from _iter_records_from_file(
            path,
            download_done=download_done,
            download_error=download_error,
            stop_event=stop_event,
            report_url=report_url,
        )
        if download_error:
            _raise_download_error(download_error[0], report_url)
    finally:
        stop_event.set()
        if not download_done.wait(timeout=10):
            logger.warning("Workday report download did not stop within 10 seconds")
        downloader.join(timeout=10)
        try:
            os.remove(path)
        except OSError:
            logger.warning("Failed to remove temporary report file %s", path)


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
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise_fatal(map_http_error(exc, report_url, xsds_request=True))
    except requests.exceptions.ConnectionError as exc:
        raise_fatal(map_connection_error(exc, report_url))
    else:
        return response.text
