"""Tests for HTTP request timeout configuration."""

from tap_workday_raas.client import (
    DEFAULT_REQUEST_TIMEOUT,
    _requests_timeout_kwargs,
    resolve_request_timeout,
)


def test_resolve_request_timeout_default() -> None:
    assert resolve_request_timeout({}) == DEFAULT_REQUEST_TIMEOUT


def test_resolve_request_timeout_custom() -> None:
    assert resolve_request_timeout({"request_timeout": 3600}) == 3600.0


def test_resolve_request_timeout_null_disables() -> None:
    assert resolve_request_timeout({"request_timeout": None}) is None


def test_requests_timeout_kwargs_omits_when_none() -> None:
    assert _requests_timeout_kwargs(None) == {}


def test_requests_timeout_kwargs_includes_value() -> None:
    assert _requests_timeout_kwargs(300.0) == {"timeout": 300.0}
