"""Tests for Workday error mapping."""

import pytest
import requests
from singer_sdk.exceptions import FatalAPIError

from tap_workday_raas.client import download_xsd, stream_report
from tap_workday_raas.exceptions import map_connection_error, map_http_error


def test_map_http_error_401() -> None:
    response = requests.Response()
    response.status_code = 401
    exc = requests.exceptions.HTTPError(
        "401 Client Error: Unauthorized for url: https://example.com",
        response=response,
    )
    err = map_http_error(exc, "https://example.com/report")
    assert err.code == "workday.InvalidUsernameOrPassword"


def test_map_http_error_xsd_500() -> None:
    response = requests.Response()
    response.status_code = 500
    exc = requests.exceptions.HTTPError(
        "500 Server Error: Internal Server Error for url: https://example.com",
        response=response,
    )
    err = map_http_error(exc, "https://example.com/report", xsds_request=True)
    assert err.code == "workdayRaaS.WorkdayRaaSInvalidReportURL"


def test_map_connection_error_dns() -> None:
    exc = requests.exceptions.ConnectionError("Name or service not known")
    err = map_connection_error(exc, "https://bad.example.com/report")
    assert err.code == "workdayRaaS.WorkdayRaaSInvalidReportURL"


def test_map_connection_error_generic() -> None:
    exc = requests.exceptions.ConnectionError("Connection reset by peer")
    err = map_connection_error(exc, "https://example.com/report")
    assert err.code == "workday.ConnectionFailed"


def test_stream_report_raises_fatal_on_401(requests_mock) -> None:  # noqa: ANN001
    requests_mock.get(
        "https://example.com/report",
        status_code=401,
    )
    with pytest.raises(FatalAPIError, match="workday.InvalidUsernameOrPassword"):
        list(stream_report("https://example.com/report", "user", "pass"))


def test_download_xsd_raises_fatal_on_500(requests_mock) -> None:  # noqa: ANN001
    requests_mock.get(
        "https://example.com/report?xsds",
        status_code=500,
    )
    with pytest.raises(FatalAPIError, match="workdayRaaS.WorkdayRaaSInvalidReportURL"):
        download_xsd("https://example.com/report?Prompt=1", "user", "pass")
