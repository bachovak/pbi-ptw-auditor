# pbi-ptw-auditor

**Inventory every Power BI report published to the open internet in your tenant.**

[![CI](https://github.com/bachovak/pbi-ptw-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/bachovak/pbi-ptw-auditor/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

Power BI's "Publish to web" feature lets users embed live reports on any public website — no authentication required. **Disabling the tenant setting does not retroactively unpublish existing embed codes.** Reports that were shared before the setting was turned off continue to serve data to the open internet indefinitely, and the Power BI service UI provides no list of them.

`pbi-ptw-auditor` solves this by querying the Power BI Admin REST API and producing a full, auditable inventory of every `PublishToWeb` embed code active in your tenant. It is **strictly read-only**: it never revokes embed codes, deletes anything, or mutates tenant state.

---

## Features

- **Complete inventory** via `GET admin/widelySharedArtifacts/publishedToWeb` with correct continuationToken pagination.
- **Workspace & dataset enrichment** using `admin/reports` and `admin/groups`.
- **Optional deep scan** (`--deep-scan`) with the metadata scanner API for sensitivity labels and datasource types.
- **Risk flags**: production workspace, missing sensitivity label, sensitive data source — all documented, configurable, and shown per row.
- **Three output formats**: CSV, JSON (with run metadata block), self-contained HTML with sortable/filterable table.
- **Email redaction** (`--redact`) for safe external sharing of the HTML report.
- **Service principal or device-code auth** — no hardcoded credentials.

---

## Prerequisites

### 1. Entra app registration

Create an app registration in Microsoft Entra (Azure AD):

1. Go to **Azure portal → Microsoft Entra ID → App registrations → New registration**.
2. Name it (e.g. `pbi-ptw-auditor`), single-tenant, no redirect URI needed.
3. Under **Certificates & secrets**, create a client secret. Note the value immediately.
4. Note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page.

The app registration needs **no API permissions** in Entra — Power BI Admin access is granted via the tenant setting below, not via Entra roles.

### 2. Power BI tenant setting: read-only admin APIs for service principals

1. In the **Power BI Admin portal → Tenant settings**, find **"Service principals can use read-only Power BI admin APIs"**.
2. Enable it and scope it to a security group.
3. Add your app registration's service principal to that security group (search by the app's display name in Entra).

> **Device-code auth**: skip step 3. Instead, the user running the tool must be a **Power BI Admin**, **Fabric Admin**, or **Global Admin** in the tenant.

### 3. Required admin role

For device-code auth the authenticating user must be one of:

- Power BI Administrator
- Microsoft Fabric Administrator
- Global Administrator

### 4. Deep scan (optional, `--deep-scan` flag)

The metadata scanner API requires two additional tenant settings to be enabled:

- **Admin portal → Tenant settings → "Enhanced metadata scanning"** → enable "Allow service principals to use read-only Power BI admin APIs" (should already be on from step 2) and ensure "Enable enhanced metadata scanning" is on.

Without these settings, `--deep-scan` will fail or return empty results.

---

## Installation

```bash
# From PyPI (once published):
pip install pbi-ptw-auditor

# From source:
git clone https://github.com/bachovak/pbi-ptw-auditor.git
cd pbi-ptw-auditor
pip install -e .
```

Requires Python 3.11 or later.

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```dotenv
PBI_TENANT_ID=00000000-0000-0000-0000-000000000000
PBI_CLIENT_ID=00000000-0000-0000-0000-000000000000
PBI_CLIENT_SECRET=your-client-secret-here
```

The tool reads these via `python-dotenv` so you don't need to export them manually.
Alternatively, set them as real environment variables (useful in CI/CD).

---

## Usage

```
Usage: pbi-ptw-auditor [OPTIONS]

  Inventory every Power BI report published to the open web in your tenant.

Options:
  --auth [service-principal|device-code]
                                  Authentication method.  [default: service-principal]
  --deep-scan                     Enable the metadata scanner (sensitivity labels,
                                  datasource types). Requires Enhanced metadata
                                  scanning tenant settings.
  --output-dir TEXT               Directory to write output files into.  [default: ./output]
  --formats TEXT                  Comma-separated output formats: csv, json, html.
                                  [default: csv,json,html]
  --no-flags                      Disable all risk flag evaluation.
  --redact                        Mask sharer email addresses in all outputs.
  --prod-workspace-regex TEXT     Case-insensitive regex for production workspaces.
                                  [default: prod|production]
  --log-level [DEBUG|INFO|WARNING|ERROR]
                                  Logging verbosity.  [default: INFO]
  --help                          Show this message and exit.
```

### Examples

**Service principal auth — all formats, default output directory:**

```bash
pbi-ptw-auditor --auth service-principal
```

**Interactive login, deep scan, emails redacted, CSV only:**

```bash
pbi-ptw-auditor --auth device-code --deep-scan --redact --formats csv
```

**Custom production workspace regex, JSON only, verbose logging:**

```bash
pbi-ptw-auditor \
  --prod-workspace-regex "prod|prd|live" \
  --formats json \
  --log-level DEBUG
```

**No flags, HTML only, custom output directory:**

```bash
pbi-ptw-auditor --no-flags --formats html --output-dir /tmp/audit-results
```

---

## Output

All files are written to `./output/` (or `--output-dir`) with a UTC timestamp in the filename, e.g. `ptw_audit_20260102_090000.csv`.

### CSV

One flat row per report. Columns:

| Column | Description |
|--------|-------------|
| `artifactId` | Report GUID |
| `displayName` | Report display name |
| `workspaceName` | Workspace name (from admin/groups) |
| `webUrl` / `embedUrl` | Direct links to the report |
| `sharerName` / `sharerEmail` | Who created the embed code |
| `sensitivityLabel` | MIP label name (deep scan only) |
| `datasetSourceTypes` | Pipe-separated datasource types |
| `flags` | Pipe-separated fired flag names |
| `enrichment_status` | `ok` or `partial` |

### JSON

Structured output with a `run_metadata` block (timestamp, tenant ID, auth method, counts) and a `reports` array with all fields above in structured form.

### HTML

A single self-contained file (inline CSS + vanilla JS, Google Fonts only external dependency) with:

- **Summary cards**: total public reports, flagged count, reports without sensitivity label, distinct sharers, distinct workspaces.
- **Sortable, filterable table**: click any column header to sort; use the search box and flag filter dropdown to narrow results.
- **Flag badges**: colour-coded pills for each risk flag.

---

## Risk flags

Flags are heuristics — they identify reports that *may* warrant review, not definitive violations. Every flag fires transparently (shown per row) and can be disabled or tuned.

| Flag | When it fires | Default | Deep scan required |
|------|---------------|---------|-------------------|
| `production_workspace` | Workspace name matches `prod\|production` (configurable via `--prod-workspace-regex`) | ✅ | No |
| `no_sensitivity_label` | Dataset has no MIP sensitivity label | ✅ | Yes |
| `sensitive_source` | Dataset is bound to a high-risk datasource type (SQL, DirectLake, Lakehouse, …) | ✅ | Yes |

Disable all flags with `--no-flags`. The flag rules and watchlists live in [`pbi_ptw_auditor/flags.py`](pbi_ptw_auditor/flags.py) — easy to extend.

---

## Read-only safety guarantee

The API client (`api_client.py`) enforces a hard read-only constraint at runtime:

- All requests are GET except one explicitly allowlisted POST: `admin/workspaces/getInfo` (the metadata scanner, which is a read-only metadata retrieval, not a mutation).
- Any attempt to call DELETE, PATCH, PUT, or an un-allowlisted POST raises `PermissionError` before the request is sent.

No embed codes are revoked. No tenant state is changed.

---

## Development

```bash
git clone https://github.com/bachovak/pbi-ptw-auditor.git
cd pbi-ptw-auditor
pip install -e ".[dev]"

# Run tests (no live tenant required — all HTTP is mocked)
pytest

# Lint
ruff check .
```

### Project layout

```
pbi_ptw_auditor/
  cli.py            # click entrypoint
  auth.py           # service-principal + device-code token acquisition
  api_client.py     # base URL, pagination, retry/backoff, read-only guard
  retrieve.py       # publishedToWeb pull
  enrich.py         # admin/reports + admin/groups join + optional scanner
  flags.py          # heuristic risk flags, configurable
  models.py         # pydantic models
  utils.py          # shared helpers (email redaction)
  reporters/
    csv_reporter.py
    json_reporter.py
    html_reporter.py
    templates/report.html.j2
tests/
  test_pagination.py    # pagination loop + continuationUri gotcha
  test_flags.py         # flag heuristics
  test_enrich_join.py   # report/workspace join
```

<!-- FUTURE: Scheduled exposure-audit workflow
When ready, add a GitHub Actions workflow (e.g. .github/workflows/scheduled-audit.yml)
triggered on a cron schedule that:
  1. Runs pbi-ptw-auditor with service-principal auth (credentials in Actions secrets).
  2. Commits the JSON snapshot to a `snapshots/` branch.
  3. Diffs against the previous snapshot and opens a GitHub issue if new public reports appear.
This enables continuous monitoring without manual re-runs.
-->

---

## Contributing

1. Fork the repo and create a feature branch.
2. Add or update tests — no live tenant is needed, use `respx` to mock HTTP.
3. Run `ruff check .` and `pytest` before opening a PR.
4. Keep changes focused; one concern per PR.

---

## Licence

MIT — see [LICENSE](LICENSE). Copyright © 2026 Kristina Bachová.
