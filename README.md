# tap-workday-raas

Singer tap for extracting data from [Workday Report-as-a-Service (RaaS)](https://www.workday.com/) custom reports. Built with the [Meltano Singer SDK](https://sdk.meltano.com).

Each configured report becomes a Singer stream. Schemas are discovered from Workday XSD metadata. Report data is streamed as JSON and emitted in Singer format for loading into warehouses such as Snowflake.

## Installation

```bash
uv sync
```

## Configuration

Create a `config.json` file:

```json
{
  "username": "workday_username",
  "password": "workday_password",
  "request_timeout": 300,
  "reports": [
    {
      "report_name": "posted_transactions",
      "report_url": "https://wd2-impl-services1.workday.com/ccx/service/customreport2/tenant/user/ReportName",
      "key_properties": ["Transaction_ID"],
      "state_param": "Posted_Date",
      "replication_key": "Posted_Date",
      "start_date": "2024-06-01T00:00:00Z",
      "state_param_format": "datetime"
    },
    {
      "report_name": "employee_snapshot",
      "report_url": "https://wd2-impl-services1.workday.com/ccx/service/customreport2/tenant/user/Employees",
      "key_properties": ["Employee_ID"]
    }
  ]
}
```

### Top-level settings

| Setting | Required | Description |
|---------|----------|-------------|
| `username` | Yes | Workday username (HTTP Basic Auth) |
| `password` | Yes | Workday password |
| `reports` | Yes | Array of report definitions |
| `request_timeout` | No | HTTP timeout in seconds for report and schema requests (default: `300`). Set to `null` for no timeout. |

### Report object

| Setting | Required | Description |
|---------|----------|-------------|
| `report_name` | Yes | Singer stream name |
| `report_url` | Yes | Full Workday custom report URL |
| `key_properties` | No | Primary key fields |
| `state_param` | No | Query param to inject bookmark into (incremental) |
| `replication_key` | No | Field whose max value becomes next bookmark |
| `start_date` | No | Initial datetime bookmark for the first incremental sync |
| `start_value` | No | Initial numeric or string bookmark for the first incremental sync |
| `state_param_format` | No | Format for datetime bookmarks in the report URL (default: `datetime`) |

#### `state_param_format` values

| Value | Workday pattern | Example |
|-------|-----------------|---------|
| `date` | `yyyy-MM-dd` | `2024-06-01` |
| `datetime` | ISO 8601 with milliseconds | `2026-06-29T07:00:00.000-07:00` or `2025-07-01T00:00:00.000Z` (UTC) |

Only applies when the bookmark value is a date or datetime. Numeric and string bookmarks are passed through unchanged.

When both `state_param` and `replication_key` are set, the stream uses **incremental** replication. Workday filters data server-side via the injected URL parameter. Otherwise the stream is **full table**.

Numeric bookmark example:

```json
{
  "report_name": "ledger_entries",
  "report_url": "https://.../LedgerReport",
  "state_param": "Last_Entry_ID",
  "replication_key": "Entry_ID",
  "start_value": "0"
}
```

See [.env.example](.env.example) for environment variable names when using Meltano.

## Usage

```bash
# Discover available streams and schemas
tap-workday-raas --config config.json --discover > catalog.json

# Sync selected streams
tap-workday-raas --config config.json --catalog catalog.json --state state.json
```

### Meltano

```bash
meltano install
meltano invoke tap-workday-raas --discover
meltano run tap-workday-raas target-jsonl
```

## Development

```bash
uv sync
uv run pytest
```

## License

This project is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later).

The [Meltano Singer SDK](https://github.com/meltano/sdk) is used as a dependency under the MIT License.

## Acknowledgments

This project is based on [singer-io/tap-workday-raas](https://github.com/singer-io/tap-workday-raas), originally developed by Stitch for extracting data from Workday Report-as-a-Service (RaaS) endpoints. Core concepts ported include XSD-driven schema discovery, streaming `Report_Entry` JSON parsing, and Workday-specific error handling. Modifications include migration to the Meltano Singer SDK and incremental sync via URL state injection.

See [NOTICE](NOTICE) for full attribution.
