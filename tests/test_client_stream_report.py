"""Tests for disk-buffered report streaming."""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
from unittest.mock import patch

from typing_extensions import override

import pytest

from tap_workday_raas.client import stream_report

SAMPLE_REPORT = {
    "Report_Entry": [
        {"Entry_ID": "1", "Posted_Date": "2024-01-01"},
        {"Entry_ID": "2", "Posted_Date": "2024-01-02"},
    ],
}


class _SlowBytesIO(io.BytesIO):
    """Byte stream that pauses on read to simulate a slow HTTP download."""

    @override
    def read(self, size: int | None = -1) -> bytes:
        time.sleep(0.01)
        return super().read(size)


class _VerySlowBytesIO(io.BytesIO):
    """Byte stream that drips slowly so abort can happen mid-download."""

    @override
    def read(self, size: int | None = -1) -> bytes:
        time.sleep(0.2)
        return super().read(32)

def test_stream_report_yields_records(requests_mock) -> None:  # noqa: ANN001
    requests_mock.get(
        "https://example.com/report",
        content=json.dumps(SAMPLE_REPORT).encode(),
    )
    records = list(stream_report("https://example.com/report", "user", "pass"))
    assert records == SAMPLE_REPORT["Report_Entry"]


def test_stream_report_removes_temp_file(requests_mock) -> None:  # noqa: ANN001
    requests_mock.get(
        "https://example.com/report",
        content=json.dumps(SAMPLE_REPORT).encode(),
    )
    created_paths: list[str] = []

    original_mkstemp = tempfile.mkstemp

    def tracking_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,  # noqa: A002
        text: bool = False,
    ) -> tuple[int, str]:
        fd, path = original_mkstemp(suffix=suffix, prefix=prefix, dir=dir, text=text)
        created_paths.append(path)
        return fd, path

    with patch("tap_workday_raas.client.tempfile.mkstemp", side_effect=tracking_mkstemp):
        list(stream_report("https://example.com/report", "user", "pass"))

    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])


def test_stream_report_parses_while_download_is_in_progress(requests_mock) -> None:  # noqa: ANN001
    payload = json.dumps(SAMPLE_REPORT).encode()
    requests_mock.get(
        "https://example.com/report",
        body=_SlowBytesIO(payload),
    )
    records = list(stream_report("https://example.com/report", "user", "pass"))
    assert records == SAMPLE_REPORT["Report_Entry"]


def test_stream_report_logs_zero_record_report(requests_mock, caplog) -> None:  # noqa: ANN001
    requests_mock.get(
        "https://example.com/report",
        content=json.dumps({"Other": []}).encode(),
    )
    with caplog.at_level("INFO"):
        records = list(stream_report("https://example.com/report", "user", "pass"))
    assert records == []
    assert "Report returned zero records" in caplog.text


def test_stream_report_raises_on_truncated_download(requests_mock) -> None:  # noqa: ANN001
    from ijson.common import IncompleteJSONError  # type: ignore[import-untyped]

    truncated = b'{"Report_Entry": [{"Entry_ID": "1"}, {"Entry_ID": "2"}, '
    requests_mock.get(
        "https://example.com/report",
        content=truncated,
    )
    with pytest.raises(IncompleteJSONError):
        list(stream_report("https://example.com/report", "user", "pass"))


def test_stream_report_close_does_not_wait_for_full_download(requests_mock) -> None:  # noqa: ANN001
    large_report = {
        "Report_Entry": [{"Entry_ID": str(index)} for index in range(50)],
    }
    requests_mock.get(
        "https://example.com/report",
        body=_VerySlowBytesIO(json.dumps(large_report).encode()),
    )

    generator = stream_report("https://example.com/report", "user", "pass")
    next(generator)
    started = time.monotonic()
    generator.close()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
