"""Tests for the deep-scan fail-safe: detect_detailed_metadata_available.

Verifies that:
  1. detect_detailed_metadata_available returns False when no enriched report
     carries a sensitivity label or datasource type.
  2. When metadata is unavailable, metadata-dependent flags become indeterminate
     rather than firing on empty data.
  3. --no-deep-scan skips the scanner entirely; metadata flags are simply not
     evaluated (neither fired nor indeterminate).
  4. production_workspace fires regardless of metadata availability.
"""

from __future__ import annotations

from pbi_ptw_auditor.enrich import detect_detailed_metadata_available, enrich_reports
from pbi_ptw_auditor.flags import (
    FLAG_NO_SENSITIVITY_LABEL,
    FLAG_PRODUCTION_WORKSPACE,
    FLAG_SENSITIVE_SOURCE,
    FlagConfig,
    apply_flags,
)
from pbi_ptw_auditor.models import EnrichedReport, PublishedReport, Sharer

# ── Helpers ────────────────────────────────────────────────────────────────────


def _sharer(**kwargs) -> Sharer:
    defaults = dict(displayName="Alice", identifier="alice-id", principalType="User")
    defaults.update(kwargs)
    return Sharer(**defaults)


def _raw_report(artifact_id: str = "r1", workspace: str = "ws-1") -> PublishedReport:
    return PublishedReport(
        artifactId=artifact_id,
        displayName="Report",
        sharer=_sharer(),
    )


def _make_enriched(
    *,
    sensitivityLabel: str | None = None,
    datasetSourceTypes: list[str] | None = None,
    workspaceName: str | None = None,
) -> EnrichedReport:
    return EnrichedReport(
        artifactId="r1",
        displayName="Report",
        sharer=_sharer(),
        sensitivityLabel=sensitivityLabel,
        datasetSourceTypes=datasetSourceTypes or [],
        workspaceName=workspaceName,
    )


_CONFIG = FlagConfig()


# ── detect_detailed_metadata_available ────────────────────────────────────────


def test_metadata_available_when_label_present() -> None:
    reports = [_make_enriched(sensitivityLabel="Confidential")]
    assert detect_detailed_metadata_available(reports) is True


def test_metadata_available_when_source_types_present() -> None:
    reports = [_make_enriched(datasetSourceTypes=["Sql"])]
    assert detect_detailed_metadata_available(reports) is True


def test_metadata_available_when_any_report_has_data() -> None:
    reports = [
        _make_enriched(),  # no label, no sources
        _make_enriched(sensitivityLabel="Internal"),
    ]
    assert detect_detailed_metadata_available(reports) is True


def test_metadata_unavailable_when_all_reports_empty() -> None:
    """All reports lack label and source data → enhanced metadata scanning is off."""
    reports = [_make_enriched(), _make_enriched(), _make_enriched()]
    assert detect_detailed_metadata_available(reports) is False


def test_metadata_available_empty_list() -> None:
    """No reports at all — can't determine either way; treat as available (no false positives)."""
    assert detect_detailed_metadata_available([]) is False


# ── Indeterminate flags when metadata unavailable ─────────────────────────────


def test_no_label_indeterminate_not_fired_when_metadata_unavailable() -> None:
    report = _make_enriched(sensitivityLabel=None)
    result = apply_flags(report, _CONFIG, deep_scan=True, detailed_metadata_available=False)
    assert FLAG_NO_SENSITIVITY_LABEL not in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL in result.indeterminate


def test_sensitive_source_indeterminate_not_fired_when_metadata_unavailable() -> None:
    report = _make_enriched(datasetSourceTypes=["Sql"])
    result = apply_flags(report, _CONFIG, deep_scan=True, detailed_metadata_available=False)
    assert FLAG_SENSITIVE_SOURCE not in result.fired
    assert FLAG_SENSITIVE_SOURCE in result.indeterminate


def test_prod_workspace_fires_regardless_of_metadata() -> None:
    report = _make_enriched(workspaceName="Production Analytics")
    result = apply_flags(report, _CONFIG, deep_scan=True, detailed_metadata_available=False)
    assert FLAG_PRODUCTION_WORKSPACE in result.fired
    assert FLAG_PRODUCTION_WORKSPACE not in result.indeterminate


def test_all_metadata_flags_indeterminate_prod_still_fires() -> None:
    """Combined: prod fires, label+source are both indeterminate."""
    report = _make_enriched(
        workspaceName="production",
        sensitivityLabel=None,
        datasetSourceTypes=["Sql"],
    )
    result = apply_flags(report, _CONFIG, deep_scan=True, detailed_metadata_available=False)
    assert FLAG_PRODUCTION_WORKSPACE in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL in result.indeterminate
    assert FLAG_SENSITIVE_SOURCE in result.indeterminate
    assert FLAG_NO_SENSITIVITY_LABEL not in result.fired
    assert FLAG_SENSITIVE_SOURCE not in result.fired


# ── --no-deep-scan: flags simply not evaluated ────────────────────────────────


def test_no_deep_scan_metadata_flags_not_fired_and_not_indeterminate() -> None:
    """With deep_scan=False no metadata flags fire and none are indeterminate."""
    report = _make_enriched(sensitivityLabel=None, datasetSourceTypes=["Sql"])
    result = apply_flags(report, _CONFIG, deep_scan=False)
    assert FLAG_NO_SENSITIVITY_LABEL not in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL not in result.indeterminate
    assert FLAG_SENSITIVE_SOURCE not in result.fired
    assert FLAG_SENSITIVE_SOURCE not in result.indeterminate


def test_no_deep_scan_prod_workspace_still_fires() -> None:
    """production_workspace must fire even when deep_scan=False."""
    report = _make_enriched(workspaceName="prod-analytics")
    result = apply_flags(report, _CONFIG, deep_scan=False)
    assert FLAG_PRODUCTION_WORKSPACE in result.fired


# ── enrich + detect round-trip ────────────────────────────────────────────────


def test_enrich_then_detect_metadata_unavailable() -> None:
    """Full round-trip: scan returns no detail → detect returns False."""
    raw = [_raw_report()]
    admin_reports = {
        "r1": {"id": "r1", "webUrl": "https://...", "embedUrl": "https://...",
               "datasetId": "ds1", "workspaceId": "ws1"}
    }
    admin_groups = {"ws1": {"id": "ws1", "name": "Finance"}}
    # Scan result with empty label and no datasources
    scan_results = {
        "ws1": {
            "id": "ws1",
            "datasets": [{"id": "ds1", "sensitivityLabel": None, "datasourceUsages": []}],
        }
    }

    enriched = enrich_reports(raw, admin_reports, admin_groups, scan_results)
    assert detect_detailed_metadata_available(enriched) is False


def test_enrich_then_detect_metadata_available() -> None:
    """Full round-trip: scan returns a label → detect returns True."""
    raw = [_raw_report()]
    admin_reports = {
        "r1": {"id": "r1", "webUrl": "https://...", "embedUrl": "https://...",
               "datasetId": "ds1", "workspaceId": "ws1"}
    }
    admin_groups = {"ws1": {"id": "ws1", "name": "Finance"}}
    scan_results = {
        "ws1": {
            "id": "ws1",
            "datasets": [
                {
                    "id": "ds1",
                    "sensitivityLabel": {"labelName": "Confidential"},
                    "datasourceUsages": [{"datasourceType": "Sql"}],
                }
            ],
        }
    }

    enriched = enrich_reports(raw, admin_reports, admin_groups, scan_results)
    assert detect_detailed_metadata_available(enriched) is True
