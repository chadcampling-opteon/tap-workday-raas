"""WorkdayRaas entry point."""

from __future__ import annotations

from tap_workday_raas.tap import TapWorkdayRaas

TapWorkdayRaas.cli()
