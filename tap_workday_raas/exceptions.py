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

"""Workday RaaS tap exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from singer_sdk.exceptions import FatalAPIError

if TYPE_CHECKING:
    from requests.exceptions import HTTPError


class WorkdayRaasError(Exception):
    """Structured error with a machine-readable Workday code."""

    def __init__(
        self,
        message: str,
        code: str,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def raise_fatal(error: WorkdayRaasError) -> NoReturn:
    """Raise an SDK fatal error preserving the Workday error code."""
    msg = f"[{error.code}] {error}"
    raise FatalAPIError(msg) from error


def map_http_error(
    exc: HTTPError,
    report_url: str,
    *,
    xsds_request: bool = False,
) -> WorkdayRaasError:
    """Map a requests HTTPError to a WorkdayRaasError."""
    response = exc.response
    if response is not None:
        if response.status_code == 401:
            return WorkdayRaasError(
                "The username or password provided is incorrect. Please check and try again",
                "workday.InvalidUsernameOrPassword",
            )
        if xsds_request and response.status_code == 500:
            return WorkdayRaasError(
                "Sorry, we couldn't access your report. Verify your report URL and name "
                "and try again.",
                "workdayRaaS.WorkdayRaaSInvalidReportURL",
            )
        if response.text:
            return WorkdayRaasError(
                f"Import failed with the following WorkdayRaaS error: {response.text}",
                "workday.WorkdayApiError",
            )

    err_text = str(exc)
    if "401 Client Error: Unauthorized for url" in err_text:
        return WorkdayRaasError(
            "The username or password provided is incorrect. Please check and try again",
            "workday.InvalidUsernameOrPassword",
        )
    if xsds_request and "500 Server Error: Internal Server Error for url" in err_text:
        return WorkdayRaasError(
            "Sorry, we couldn't access your report. Verify your report URL and name "
            "and try again.",
            "workdayRaaS.WorkdayRaaSInvalidReportURL",
        )
    return WorkdayRaasError(str(exc), "workday.WorkdayApiError")


def map_connection_error(exc: ConnectionError, report_url: str) -> WorkdayRaasError:
    """Map a requests ConnectionError to a WorkdayRaasError."""
    message = str(exc)
    if (
        "nodename nor servname provided, or not known" in message
        or "Name or service not known" in message
    ):
        return WorkdayRaasError(
            f'The report URL "{report_url}" was not found. Please check the report URL '
            "and try again.",
            "workdayRaaS.WorkdayRaaSInvalidReportURL",
        )
    return WorkdayRaasError(
        f'Sorry, we couldn\'t connect to the specified report URL "{report_url}". '
        "Please ensure all the connection form values are correct.",
        "workday.ConnectionFailed",
    )
