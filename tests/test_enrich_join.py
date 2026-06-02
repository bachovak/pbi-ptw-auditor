"""Tests for the report/workspace enrichment join in pbi_ptw_auditor.enrich."""

from __future__ import annotations

from pbi_ptw_auditor.enrich import enrich_reports
from pbi_ptw_auditor.models import PublishedReport, Sharer

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _sharer(**kwargs) -> Sharer:
    defaults = dict(displayName="Alice", identifier="alice-id", principalType="User")
    defaults.update(kwargs)
    return Sharer(**defaults)


def _raw_report(artifact_id: str = "report-1", **kwargs) -> PublishedReport:
    return PublishedReport(
        artifactId=artifact_id,
        displayName=kwargs.get("displayName", "Report One"),
        sharer=kwargs.get("sharer", _sharer()),
    )


_ADMIN_REPORTS: dict = {
    "report-1": {
        "id": "report-1",
        "name": "Report One",
        "webUrl": "https://app.powerbi.com/reports/report-1",
        "embedUrl": "https://app.powerbi.com/reportEmbed?reportId=report-1",
        "datasetId": "dataset-1",
        "workspaceId": "workspace-1",
    }
}

_ADMIN_GROUPS: dict = {
    "workspace-1": {"id": "workspace-1", "name": "Finance - Production"}
}


# ── Basic join ─────────────────────────────────────────────────────────────────


def test_enrich_joins_web_url() -> None:
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].webUrl == "https://app.powerbi.com/reports/report-1"


def test_enrich_joins_embed_url() -> None:
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert "reportEmbed" in (enriched[0].embedUrl or "")


def test_enrich_joins_dataset_id() -> None:
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].datasetId == "dataset-1"


def test_enrich_joins_workspace_id() -> None:
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].workspaceId == "workspace-1"


def test_enrich_joins_workspace_name() -> None:
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].workspaceName == "Finance - Production"


def test_enrichment_status_ok_when_report_found() -> None:
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].enrichment_status == "ok"


# ── Degraded / partial enrichment ─────────────────────────────────────────────


def test_enrichment_status_partial_when_report_not_in_admin() -> None:
    """Report exists in publishedToWeb but not in admin/reports → partial."""
    enriched = enrich_reports([_raw_report("unknown-id")], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].enrichment_status == "partial"
    assert enriched[0].webUrl is None
    assert enriched[0].workspaceId is None


def test_workspace_name_none_when_group_not_found() -> None:
    """Report found in admin/reports but workspace not in admin/groups."""
    admin_reports = {
        "report-1": {
            "id": "report-1",
            "webUrl": "https://...",
            "embedUrl": "https://...",
            "datasetId": "ds-1",
            "workspaceId": "orphan-workspace",
        }
    }
    enriched = enrich_reports([_raw_report()], admin_reports, {})
    assert enriched[0].workspaceName is None
    assert enriched[0].workspaceId == "orphan-workspace"
    assert enriched[0].enrichment_status == "ok"


# ── Multiple reports ───────────────────────────────────────────────────────────


def test_enrich_multiple_reports() -> None:
    reports = [_raw_report("report-1"), _raw_report("report-2", displayName="Report Two")]
    admin_reports = {
        **_ADMIN_REPORTS,
        "report-2": {
            "id": "report-2",
            "webUrl": "https://app.powerbi.com/reports/report-2",
            "embedUrl": "https://app.powerbi.com/reportEmbed?reportId=report-2",
            "datasetId": "dataset-2",
            "workspaceId": "workspace-1",
        },
    }
    enriched = enrich_reports(reports, admin_reports, _ADMIN_GROUPS)

    assert len(enriched) == 2
    assert enriched[0].artifactId == "report-1"
    assert enriched[1].artifactId == "report-2"
    # Both share the same workspace
    assert enriched[0].workspaceName == enriched[1].workspaceName == "Finance - Production"


def test_enrich_empty_input() -> None:
    enriched = enrich_reports([], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched == []


# ── Deep scan enrichment ───────────────────────────────────────────────────────


def test_enrich_deep_scan_sensitivity_label() -> None:
    scan_results = {
        "workspace-1": {
            "id": "workspace-1",
            "datasets": [
                {
                    "id": "dataset-1",
                    "sensitivityLabel": {"labelName": "Confidential"},
                    "datasourceUsages": [{"datasourceType": "Sql"}],
                }
            ],
        }
    }
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS, scan_results)
    assert enriched[0].sensitivityLabel == "Confidential"
    assert enriched[0].datasetSourceTypes == ["Sql"]


def test_enrich_deep_scan_no_label_returned_as_none() -> None:
    scan_results = {
        "workspace-1": {
            "id": "workspace-1",
            "datasets": [
                {
                    "id": "dataset-1",
                    "sensitivityLabel": None,
                    "datasourceUsages": [],
                }
            ],
        }
    }
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS, scan_results)
    assert enriched[0].sensitivityLabel is None


def test_enrich_deep_scan_dataset_not_in_results() -> None:
    """If the dataset isn't in the scan result, enrichment should still succeed."""
    enriched = enrich_reports([_raw_report()], _ADMIN_REPORTS, _ADMIN_GROUPS, scan_results={})
    assert enriched[0].sensitivityLabel is None
    assert enriched[0].datasetSourceTypes == []


# ── Sharer passthrough ─────────────────────────────────────────────────────────


def test_enrich_preserves_sharer_fields() -> None:
    sharer = _sharer(displayName="Bob Smith", emailAddress="bob@contoso.com", principalType="User")
    report = _raw_report("report-1", sharer=sharer)
    enriched = enrich_reports([report], _ADMIN_REPORTS, _ADMIN_GROUPS)
    assert enriched[0].sharer.displayName == "Bob Smith"
    assert enriched[0].sharer.emailAddress == "bob@contoso.com"
