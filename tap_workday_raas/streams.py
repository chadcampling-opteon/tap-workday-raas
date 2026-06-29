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
from typing import TYPE_CHECKING, Any, ClassVar

from singer_sdk.exceptions import ConfigValidationError
from singer_sdk.streams import Stream

from tap_workday_raas.client import (
    apply_format_json,
    build_report_url,
    resolve_request_timeout,
    stream_report,
)
from tap_workday_raas.datetime_formats import DEFAULT_BOOKMARK_FORMAT
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
    state_param_format: ClassVar[str] = DEFAULT_BOOKMARK_FORMAT
    report_config: ClassVar[Mapping[str, Any]]

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

    @override
    def get_records(self, context: Context | None) -> Iterable[dict]:
        """Fetch records from the Workday report URL."""
        url = self.resolve_sync_url(context)
        username = self.config["username"]
        password = self.config["password"]
        timeout = resolve_request_timeout(self.config)

        self.logger.info('Syncing report "%s" from %s.', self.name, url)
        record_count = 0
        for record in stream_report(url, username, password, timeout=timeout):
            record_count += 1
            yield record

        self.logger.info("%s: Completed sync (%s rows)", self.name, record_count)

    @override
    def post_process(self, row: Record, context: Context | None = None) -> Record | None:
        """Coerce Workday values (booleans, decimals) before emission."""
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
        "name": report["report_name"],
        "primary_keys": tuple(key_properties),
        "schema": schema,
    }
    if incremental:
        attrs["replication_key"] = replication_key

    class_name = f"Report_{report['report_name']}_Stream"
    stream_class = type(class_name, (WorkdayRaasStream,), attrs)
    return stream_class(tap)
