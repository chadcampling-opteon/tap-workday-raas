"""Tests standard tap features using the built-in SDK tests library."""

from __future__ import annotations

from unittest.mock import patch

from singer_sdk.testing import get_tap_test_class

from tap_workday_raas.tap import TapWorkdayRaas

SAMPLE_CONFIG = {
    "username": "test_user",
    "password": "test_pass",
    "reports": [
        {
            "report_name": "test_report",
            "report_url": "https://example.workday.com/ccx/service/customreport2/tenant/user/Report",
            "key_properties": ["Entry_ID"],
        },
    ],
}

SAMPLE_XSD = """<?xml version="1.0" encoding="UTF-8"?>
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

_download_xsd_patch = patch(
    "tap_workday_raas.tap.download_xsd",
    return_value=SAMPLE_XSD,
)
_stream_report_patch = patch(
    "tap_workday_raas.streams.stream_report",
    return_value=iter([{"Entry_ID": "1"}]),
)
_download_xsd_patch.start()
_stream_report_patch.start()


def teardown_module() -> None:
    _stream_report_patch.stop()
    _download_xsd_patch.stop()


TestTapWorkdayRaas = get_tap_test_class(
    tap_class=TapWorkdayRaas,
    config=SAMPLE_CONFIG,
)
