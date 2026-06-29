"""WorkdayRaas tap class."""

from __future__ import annotations

import sys

from singer_sdk import Tap
from singer_sdk import typing as th

from tap_workday_raas.client import download_xsd, resolve_request_timeout
from tap_workday_raas.datetime_formats import BOOKMARK_FORMATS, DEFAULT_BOOKMARK_FORMAT
from tap_workday_raas.discovery import generate_schema_for_report
from tap_workday_raas.streams import WorkdayRaasStream, create_report_stream

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

REPORT_CONFIG_SCHEMA = th.PropertiesList(
    th.Property(
        "report_name",
        th.StringType(nullable=False),
        required=True,
        description="Singer stream name for this report",
    ),
    th.Property(
        "report_url",
        th.StringType(nullable=False),
        required=True,
        description="Full Workday custom report (RaaS) URL",
    ),
    th.Property(
        "key_properties",
        th.ArrayType(th.StringType(nullable=False)),
        description="Primary key fields for the stream",
    ),
    th.Property(
        "state_param",
        th.StringType,
        description="Query parameter name to inject the bookmark into for incremental sync",
    ),
    th.Property(
        "replication_key",
        th.StringType,
        description="Field whose max value becomes the next bookmark",
    ),
    th.Property(
        "start_date",
        th.DateTimeType,
        description="Initial datetime bookmark for the first incremental sync of this report",
    ),
    th.Property(
        "start_value",
        th.StringType,
        description="Initial numeric or string bookmark for the first incremental sync",
    ),
    th.Property(
        "state_param_format",
        th.StringType(allowed_values=list(BOOKMARK_FORMATS)),
        default=DEFAULT_BOOKMARK_FORMAT,
        description=(
            "Workday format for datetime bookmarks in the report URL: "
            "'date' (yyyy-MM-dd) or 'datetime' (ISO 8601 with milliseconds)"
        ),
    ),
)


class TapWorkdayRaas(Tap):
    """Singer tap for Workday Report-as-a-Service (RaaS)."""

    name = "tap-workday-raas"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "username",
            th.StringType(nullable=False),
            required=True,
            title="Username",
            description="Workday account username for HTTP Basic Auth",
        ),
        th.Property(
            "password",
            th.StringType(nullable=False),
            required=True,
            secret=True,
            title="Password",
            description="Workday account password for HTTP Basic Auth",
        ),
        th.Property(
            "reports",
            th.ArrayType(REPORT_CONFIG_SCHEMA),
            required=True,
            title="Reports",
            description="Workday RaaS reports to extract as Singer streams",
        ),
        th.Property(
            "request_timeout",
            th.NumberType,
            description=(
                "HTTP request timeout in seconds for report and schema downloads. "
                "Omit for the default (300). Set to null for no timeout."
            ),
        ),
    ).to_dict()

    @override
    def discover_streams(self) -> list[WorkdayRaasStream]:
        """Return a list of discovered streams from configured reports."""
        username = self.config["username"]
        password = self.config["password"]
        timeout = resolve_request_timeout(self.config)
        streams: list[WorkdayRaasStream] = []

        for report in self.config["reports"]:
            report_name = report["report_name"]
            self.logger.info('Downloading XSD to determine table schema "%s".', report_name)
            xsd = download_xsd(report["report_url"], username, password, timeout=timeout)
            schema = generate_schema_for_report(xsd)
            streams.append(create_report_stream(self, report, schema))

        return streams


if __name__ == "__main__":
    TapWorkdayRaas.cli()
