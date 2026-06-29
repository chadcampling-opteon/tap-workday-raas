"""Tests for Workday report streams."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from singer_sdk.exceptions import ConfigValidationError

from tap_workday_raas.streams import create_report_stream
from tap_workday_raas.tap import TapWorkdayRaas

MINIMAL_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <xsd:complexType name="Report_EntryType">
    <xsd:sequence>
      <xsd:element name="Entry_ID" type="xsd:string" minOccurs="0"/>
    </xsd:sequence>
  </xsd:complexType>
  <xsd:complexType name="Report_DataType">
    <xsd:sequence>
      <xsd:element name="Report_Entry" type="xsd:string" minOccurs="0"/>
    </xsd:sequence>
  </xsd:complexType>
</xsd:schema>
"""

SAMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "Posted_Date": {"type": ["string", "null"], "format": "date-time"},
        "Entry_ID": {"type": ["number", "null"]},
    },
}


@pytest.fixture
def tap_config() -> dict:
    return {
        "username": "user",
        "password": "pass",
        "reports": [
            {
                "report_name": "_placeholder",
                "report_url": "https://example.com/report/Placeholder",
            },
        ],
    }


@pytest.fixture
def tap(tap_config: dict) -> TapWorkdayRaas:
    with patch("tap_workday_raas.tap.download_xsd", return_value=MINIMAL_XSD):
        return TapWorkdayRaas(config=tap_config)


def test_resolve_sync_url_uses_start_date_on_first_run(tap: TapWorkdayRaas) -> None:
    report = {
        "report_name": "incremental_report",
        "report_url": "https://example.com/report/MyReport",
        "state_param": "Posted_Date",
        "replication_key": "Posted_Date",
        "start_date": "2024-01-01T00:00:00Z",
    }
    stream = create_report_stream(tap, report, SAMPLE_SCHEMA)
    url = stream.resolve_sync_url(None)
    assert "Posted_Date=2024-01-01T00%3A00%3A00.000Z" in url
    assert "format=json" in url


def test_incremental_requires_initial_bookmark(tap: TapWorkdayRaas) -> None:
    report = {
        "report_name": "no_start",
        "report_url": "https://example.com/report/Other",
        "state_param": "Entry_ID",
        "replication_key": "Entry_ID",
    }
    stream = create_report_stream(tap, report, SAMPLE_SCHEMA)
    with pytest.raises(ConfigValidationError):
        stream.resolve_initial_bookmark()


@patch("tap_workday_raas.streams.stream_report")
def test_get_records_yields_post_processed_rows(
    mock_stream_report,
    tap: TapWorkdayRaas,
) -> None:
    mock_stream_report.return_value = iter([{"Posted_Date": "2024-02-01", "Entry_ID": "1"}])
    report = {
        "report_name": "full_table",
        "report_url": "https://example.com/report/Full",
    }
    stream = create_report_stream(tap, report, SAMPLE_SCHEMA)
    records = list(stream.get_records(None))
    assert records == [{"Posted_Date": "2024-02-01", "Entry_ID": "1"}]
    mock_stream_report.assert_called_once_with(
        "https://example.com/report/Full?format=json",
        "user",
        "pass",
        timeout=300,
    )


def test_resolve_sync_url_uses_date_format(tap: TapWorkdayRaas) -> None:
    report = {
        "report_name": "date_report",
        "report_url": "https://example.com/report/MyReport",
        "state_param": "Posted_Date",
        "replication_key": "Posted_Date",
        "start_date": "2024-01-01T00:00:00Z",
        "state_param_format": "date",
    }
    stream = create_report_stream(tap, report, SAMPLE_SCHEMA)
    url = stream.resolve_sync_url(None)
    assert "Posted_Date=2024-01-01" in url
