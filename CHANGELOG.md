# Changelog

All notable changes to pbi-ptw-auditor are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.2.0] — 2026-06-02

### Changed

- **Deep scan is now the default.** A bare `pbi-ptw-auditor` run performs a full
  data-level exposure assessment — inventorying published reports, enriching them
  with workspace/dataset metadata, and running the metadata scanner for sensitivity
  labels and datasource types. Pass `--no-deep-scan` for the previous fast,
  inventory-only behaviour.
- `--deep-scan` flag replaced by a `--deep-scan / --no-deep-scan` boolean pair
  (default: `--deep-scan`). Existing scripts that passed `--deep-scan` explicitly
  continue to work unchanged.

### Added

- **Fail-safe for unavailable detailed metadata.** When the metadata scanner runs
  but returns no sensitivity labels or datasource types for any dataset (indicating
  that *Enhanced metadata scanning* / *Detailed metadata responses* is not enabled
  in the tenant), the tool now:
  - Emits a single prominent `WARNING` log line explaining the situation.
  - Marks `no_sensitivity_label` and `sensitive_source` as **indeterminate** rather
    than firing them on empty data or silently clearing them.
  - Records the warning in the `run_metadata.warnings` array of the JSON output.
  - Shows a yellow warning banner at the top of the HTML report.
  - Displays `N/A` on the "No Sensitivity Label" summary card in the HTML report.
  - `production_workspace` is unaffected and evaluates normally.
- `EnrichedReport.indeterminate_flags` — list of flag names that could not be
  evaluated due to unavailable metadata.
- `EnrichedReport.metadata_status` — per-report status: `available`, `indeterminate`,
  or `not_requested`.
- `RunMetadata.detailed_metadata_available` — tenant-level capability signal.
- `RunMetadata.warnings` — list of run-level warning messages surfaced in JSON output.
- `RunMetadata.missing_label_count` is now `Optional[int]`; `null` in JSON when
  detailed metadata is unavailable (was always an integer previously).
- New CSV columns: `indeterminate_flags`, `metadata_status`.
- New JSON report fields: `indeterminate_flags`, `metadata_status` per report;
  `detailed_metadata_available`, `warnings` in `run_metadata`.
- HTML: indeterminate flags shown as dashed grey pill badges with tooltip.
- HTML: "Metadata" column in the table showing `available` / `indeterminate` /
  `not_requested` status per report.
- `CHANGELOG.md` (this file).

### Fixed

- `missing_label_count` now correctly returns `None` (not the full report count)
  when detailed metadata is unavailable, preventing misleading statistics.

---

## [0.1.1] — 2026-06-02

### Fixed

- `publishedToWeb` endpoint returns items under `ArtifactAccessEntities`, not the
  generic `value` key used by other admin endpoints. Bare runs now correctly return
  published reports instead of an empty list.

---

## [0.1.0] — 2026-06-02

### Added

- Initial release.
- Inventory of all Power BI reports published to the open web via
  `admin/widelySharedArtifacts/publishedToWeb` with correct `continuationToken`
  pagination (never following `continuationUri`).
- Medium enrichment via `admin/reports` and `admin/groups`.
- Optional metadata scanner deep scan (sensitivity labels, datasource types).
- Risk flags: `production_workspace`, `no_sensitivity_label`, `sensitive_source`.
- CSV, JSON, and HTML output formats.
- Service-principal and device-code authentication.
- `--redact` flag for external sharing.
- MIT licence, `pyproject.toml` packaging, GitHub Actions CI (ruff + pytest).
