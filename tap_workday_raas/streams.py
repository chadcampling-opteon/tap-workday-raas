# Copyright (c) 2026 Opteon Solutions
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Stream type classes for tap-workday-raas."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar

from singer_sdk.exceptions import ConfigValidationError
from singer_sdk.streams import Stream

from tap_workday_raas.client import (
    apply_format_json,
    build_report_url,
    format_state_value,
    resolve_request_timeout,
    stream_report,
)
from tap_workday_raas.datetime_formats import DEFAULT_BOOKMARK_FORMAT, BookmarkFormat
from tap_workday_raas.paging import PageWindow, Paging, next_page_window, paging_from_report
from tap_workday_raas.transform import coerce_record

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from singer_sdk.helpers.types import Context, Record

    from tap_workday_raas.tap import TapWorkdayRaas


class WorkdayRaasStream(Stream):
    """Base stream class for Workday RaaS report streams."""

    report_url: ClassVar[str] = ""
    state_param: ClassVar[str | None] = None
    state_param_format: ClassVar[BookmarkFormat] = DEFAULT_BOOKMARK_FORMAT
    report_config: ClassVar[Mapping[str, Any]]
    paging: ClassVar[Paging | None] = None

    @property
    def is_incremental(self) -> bool:
        """Return True when this report uses URL state injection."""
        return bool(self.state_param and self.replication_key)

    def resolve_initial_bookmark(self) -> Any:
        """Resolve the first-run bookmark from the report config."""
        report = self.report_config

        if report.get("start_value") is not None:
            return report["start_value"]
        if report.get("start_date") is not None:
            return report["start_date"]

        msg = (
            f"Incremental report '{self.name}' requires an initial bookmark. "
            "Set start_value or start_date on the report."
        )
        raise ConfigValidationError(msg)

    def resolve_sync_url(self, context: Context | None) -> str:
        """Build the report URL, injecting state when configured."""
        if not self.state_param:
            return apply_format_json(self.report_url)

        bookmark = self.get_starting_replication_key_value(context)
        if bookmark is None:
            bookmark = self.resolve_initial_bookmark()

        return build_report_url(
            self.report_url,
            state_param=self.state_param,
            state_value=bookmark,
            state_param_format=self.state_param_format,
        )

    def _utc_now(self) -> datetime:
        """Return the current UTC time, split out so tests can freeze the ceiling."""
        return datetime.now(timezone.utc)

    def _iter_report(self, url: str) -> Iterable[dict]:
        """Stream one report response."""
        username = self.config["username"]
        password = self.config["password"]
        timeout = resolve_request_timeout(self.config)
        self.logger.info('Syncing report "%s" from %s.', self.name, url)
        yield from stream_report(url, username, password, timeout=timeout)

    def _page_url(self, window: PageWindow) -> str:
        """Build the report URL for one paging window."""
        paging = self.paging
        if paging is None or not self.state_param:
            msg = f"Report '{self.name}' is not configured for paging"
            raise ConfigValidationError(msg)
        return build_report_url(
            self.report_url,
            state_param=self.state_param,
            state_value=window.start,
            state_param_format=self.state_param_format,
            page_param=paging.param,
            page_value=window.end,
        )

    @override
    def get_records(self, context: Context | None) -> Iterable[dict]:
        """Fetch records from the Workday report URL."""
        if self.paging is None:
            yield from self._sync_single_request(context)
            return
        yield from self._sync_paged(context)

    def _sync_single_request(self, context: Context | None) -> Iterable[dict]:
        """Fetch the report once, leaving any end-date parameter on the URL as-is."""
        record_count = 0
        for record in self._iter_report(self.resolve_sync_url(context)):
            record_count += 1
            yield record
        self.logger.info("%s: Completed sync (%s rows)", self.name, record_count)

    def _sync_paged(self, context: Context | None) -> Iterable[dict]:
        """Walk windows in memory. The replication bookmark stays the max key seen.

        The window end is not written to state. An empty window does not mean
        that range is complete, and report rows are not assumed to be ordered
        by the replication key.
        """
        paging = self.paging
        if paging is None:
            return

        cursor = self.get_starting_replication_key_value(context)
        if cursor is None:
            cursor = self.resolve_initial_bookmark()

        total = 0
        while True:
            window = next_page_window(cursor, paging, now=self._utc_now())
            if window is None:
                self.logger.info(
                    "%s: bookmark is at or past the paging ceiling",
                    self.name,
                )
                break

            self.logger.info(
                "%s: paging window %s to %s.",
                self.name,
                format_state_value(window.start, self.state_param_format),
                format_state_value(window.end, self.state_param_format),
            )
            page_count = 0
            for record in self._iter_report(self._page_url(window)):
                page_count += 1
                total += 1
                yield record

            if window.stop_on_empty and page_count == 0:
                self.logger.info("%s: empty numeric page, stopping paging", self.name)
                break
            if window.is_last:
                break
            cursor = window.end

        self.logger.info("%s: Completed sync (%s rows)", self.name, total)

    @override
    def post_process(self, row: Record, context: Context | None = None) -> Record | None:
        """Coerce Workday values (booleans, decimals, dates) before emission."""
        coerced = coerce_record(dict(row), self.schema)
        return super().post_process(coerced, context)


def create_report_stream(
    tap: TapWorkdayRaas,
    report: Mapping[str, Any],
    schema: dict,
) -> WorkdayRaasStream:
    """Create a stream instance for a configured Workday report."""
    state_param = report.get("state_param")
    replication_key = report.get("replication_key")
    incremental = bool(state_param and replication_key)
    key_properties = report.get("key_properties") or []

    attrs: dict[str, Any] = {
        "report_url": report["report_url"],
        "state_param": state_param,
        "state_param_format": report.get("state_param_format", DEFAULT_BOOKMARK_FORMAT),
        "report_config": report,
        "paging": paging_from_report(report),
        "name": report["report_name"],
        "primary_keys": tuple(key_properties),
        "schema": schema,
    }
    if incremental:
        attrs["replication_key"] = replication_key

    class_name = f"Report_{report['report_name']}_Stream"
    stream_class = type(class_name, (WorkdayRaasStream,), attrs)
    return stream_class(tap)
