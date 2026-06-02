# pbi-ptw-auditor

**Full data-level exposure assessment for Power BI reports published to the open internet.**

[![CI](https://github.com/bachovak/pbi-ptw-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/bachovak/pbi-ptw-auditor/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

Power BI's "Publish to web" feature lets users embed live reports on any public website — no authentication required. **Disabling the tenant setting does not retroactively unpublish existing embed codes.** Reports that were shared before the setting was turned off continue to serve data to the open internet indefinitely, and the Power BI service UI provides no list of them.

`pbi-ptw-auditor` solves this by querying the Power BI Admin REST API and producing a full, auditable inventory of every `PublishToWeb` embed code active in your tenant — complete with sensitivity labels, datasource types, and risk flags. It is **strictly read-only**: it never revokes embed codes, deletes anything, or mutates tenant state.

---

## Features

- **Complete inventory** via `GET admin/widelySharedArtifacts/publishedToWeb` with correct continuationToken pagination (never follows `continuationUri`).
- **Workspace & dataset enrichment** using `admin/reports` and `admin/groups`.
- **Sensitivity labels and datasource types** via the metadata scanner API — runs by default.
- **Fail-safe metadata handling**: when the scanner runs but the tenant's enhanced metadata settings are off, metadata-dependent flags are marked **indeterminate** rather than firing on empty data or silently clearing.
- **Risk flags**: production workspace, missing sensitivity label, sensitive data source — all documented, configurable, and shown per row.
- **Three output formats**: CSV, JSON (with run metadata block), self-contained HTML with warning banner, sortable/filterable table, and indeterminate badge indicators.
- **Email redaction** (`--redact`) for safe external sharing.
- **Service principal or device-code auth** — no hardcoded credentials.
- **`--no-deep-scan`** for a faster, inventory-only run that skips the scanner.

---

## Prerequisites

### 1. Entra app registration

Create an app registration in Microsoft Entra (Azure AD):

1. Go to **Azure portal → Microsoft Entra ID → App registrations → New registration**.
2. Name it (e.g. `pbi-ptw-auditor`), single-tenant, no redirect URI needed.
3. Under **Certificates & secrets**, create a client secret. Note the value immediately.
4. Note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page.
5. Under **Authentication → Advanced settings**, set **"Allow public client flows"** to **Yes** (required for device-code auth only).

The app registration needs **no Entra API permissions** — Power BI Admin access is granted via the tenant settings below.

### 2. Power BI tenant setting: read-only admin APIs for service principals

1. In the **Power BI Admin portal → Tenant settings**, find **"Service principals can use read-only Power BI admin APIs"**.
2. Enable it and scope it to a security group.
3. Add your app registration's service principal to that security group.

> **Device-code auth**: the user signing in must be a **Power BI Administrator**, **Microsoft Fabric Administrator**, or **Global Administrator**. No security group needed.

### 3. Enhanced metadata scanning (required for the default run)

The default run calls the metadata scanner API to retrieve sensitivity labels and datasource types. Two tenant settings must be enabled for this to return data:

1. **Power BI Admin portal → Tenant settings → "Enhanced metadata scanning"** — enable it.
2. **"Allow detailed metadata responses in tenant-wide admin APIs"** (may appear as "Detailed metadata responses") — enable it.

Without these settings the scanner succeeds but returns no label or datasource detail. The tool detects this automatically and marks the affected flags as **indeterminate** rather than firing them. A warning banner appears in the HTML report. You can also run `--no-deep-scan` to skip the scanner entirely.

### 4. Required admin role

For **device-code auth** the authenticating user must be one of:

- Power BI Administrator
- Microsoft Fabric Administrator
- Global Administrator

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

---

## Usage

```
Usage: pbi-ptw-auditor [OPTIONS]

  Full data-level exposure assessment for Power BI Publish-to-Web.

  By default runs a complete assessment: inventories every report published
  to the open web, enriches it with workspace and dataset metadata, runs the
  metadata scanner for sensitivity labels and datasource types, and applies
  risk flags. Pass --no-deep-scan for a faster inventory-only run.

Options:
  --auth [service-principal|device-code]
                                  Authentication method.  [default: service-principal]
  --deep-scan / --no-deep-scan    Deep scan (default) calls the metadata scanner API for
                                  sensitivity labels and datasource types. Pass --no-deep-scan
                                  for inventory-only.  [default: deep-scan]
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

**Full exposure assessment — service principal auth (default):**

```bash
pbi-ptw-auditor --auth service-principal
```

**Fast inventory only, no scanner — interactive login:**

```bash
pbi-ptw-auditor --auth device-code --no-deep-scan
```

**Full assessment, emails redacted, HTML only (for external sharing):**

```bash
pbi-ptw-auditor --auth service-principal --redact --formats html
```

**Custom production workspace regex, JSON only, verbose logging:**

```bash
pbi-ptw-auditor \
  --prod-workspace-regex "prod|prd|live" \
  --formats json \
  --log-level DEBUG
```

---

## Output

All files are written to `./output/` (or `--output-dir`) with a UTC timestamp in the filename, e.g. `ptw_audit_20260602_090000.csv`.

### CSV

One flat row per report. Key columns:

| Column | Description |
|--------|-------------|
| `artifactId` | Report GUID |
| `displayName` | Report display name |
| `workspaceName` | Workspace name |
| `sharerName` / `sharerEmail` | Who created the embed code |
| `sensitivityLabel` | MIP label name (deep scan only) |
| `datasetSourceTypes` | Pipe-separated datasource types (deep scan only) |
| `flags` | Pipe-separated fired flag names |
| `indeterminate_flags` | Flags that could not be evaluated (metadata unavailable) |
| `metadata_status` | `available` \| `indeterminate` \| `not_requested` |
| `enrichment_status` | `ok` \| `partial` |

### JSON

Structured output. The `run_metadata` block includes:

```json
{
  "run_metadata": {
    "utc_timestamp": "...",
    "tenant_id": "...",
    "deep_scan": true,
    "detailed_metadata_available": true,
    "total_count": 12,
    "flagged_count": 3,
    "missing_label_count": 5,
    "warnings": []
  }
}
```

`missing_label_count` is `null` when `detailed_metadata_available` is `false`.
Each report object includes `flags`, `indeterminate_flags`, and `metadata_status`.

### HTML

A single self-contained file with:

- **Warning banner** (shown when `detailed_metadata_available` is `false`) explaining that enhanced metadata scanning is not enabled and flags are indeterminate.
- **Summary cards**: total public reports, flagged count, reports without sensitivity label (shows **N/A** when metadata unavailable), distinct sharers, distinct workspaces.
- **Sortable, filterable table** with flag badges (solid colour = fired, dashed grey = indeterminate) and per-row metadata status.

---

## Risk flags

Flags are heuristics — they identify reports that *may* warrant review. Every flag fires transparently (shown per row) and can be disabled or tuned.

| Flag | When it fires | Requires deep scan | Indeterminate when |
|------|---------------|-------------------|--------------------|
| `production_workspace` | Workspace name matches `prod\|production` (configurable) | No | Never |
| `no_sensitivity_label` | Dataset has no MIP sensitivity label | Yes | Enhanced metadata scanning not enabled |
| `sensitive_source` | Dataset bound to a high-risk source type (SQL, DirectLake, Lakehouse, …) | Yes | Enhanced metadata scanning not enabled |

**Indeterminate** means the flag could not be honestly evaluated — the scanner ran but returned no metadata detail. Indeterminate flags appear in `indeterminate_flags` (not `flags`) so downstream consumers can distinguish "genuinely no label" from "could not determine". A single warning is logged per run; flags are not spammed per row.

Disable all flags with `--no-flags`. Rules and watchlists live in [`pbi_ptw_auditor/flags.py`](pbi_ptw_auditor/flags.py).

---

## Read-only safety guarantee

The API client (`api_client.py`) enforces a hard read-only constraint at runtime:

- All requests are GET except one explicitly allowlisted POST: `admin/workspaces/getInfo` (the metadata scanner — read-only metadata retrieval, not a mutation).
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
  enrich.py         # admin/reports + admin/groups join; scanner; detect_detailed_metadata_available
  flags.py          # FlagResult, FlagConfig, apply_flags
  models.py         # pydantic models (EnrichedReport, RunMetadata)
  utils.py          # email redaction
  reporters/
    csv_reporter.py
    json_reporter.py
    html_reporter.py
    templates/report.html.j2
tests/
  test_pagination.py       # pagination loop + continuationUri gotcha
  test_flags.py            # flag heuristics + indeterminate state
  test_enrich_join.py      # report/workspace join
  test_deep_scan_failsafe.py  # detect_detailed_metadata_available + fail-safe logic
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
2. Add or update tests — no live tenant needed, use `respx` to mock HTTP.
3. Run `ruff check .` and `pytest` before opening a PR.
4. Keep changes focused; one concern per PR.

---

## Licence

MIT — see [LICENSE](LICENSE). Copyright © 2026 Kristina Bachová.
