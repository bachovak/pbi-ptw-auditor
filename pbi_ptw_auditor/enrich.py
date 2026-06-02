"""Enrich raw PublishedReport objects with workspace/dataset metadata.

Medium enrichment (always runs):
  - GET admin/reports  → webUrl, embedUrl, datasetId, workspaceId
  - GET admin/groups   → workspaceName

Rich enrichment (default; skipped with --no-deep-scan):
  - POST admin/workspaces/getInfo  → sensitivity labels, datasource types
    Requires "Enhanced metadata scanning" / "Detailed metadata responses"
    tenant settings to be enabled. Rate-limited; batched at 100 workspaces.

Fail-safe: if the scanner runs but returns no label or source data for any
dataset, detect_detailed_metadata_available() returns False. Callers must
then suppress metadata-dependent flags rather than firing them on empty data.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .api_client import PowerBIClient
from .models import EnrichedReport, PublishedReport

logger = logging.getLogger(__name__)

# admin/groups is heavily rate-limited (~50 req/hour); page conservatively.
_GROUPS_PAGE_SIZE = 100
_GROUPS_INTER_PAGE_SLEEP = 0.5  # seconds between pages

_SCANNER_BATCH_SIZE = 100
_SCANNER_POLL_INTERVAL = 5  # seconds between poll attempts
_SCANNER_MAX_POLLS = 30


def get_all_reports(client: PowerBIClient) -> dict[str, dict]:
    """Load all reports via admin/reports, keyed by report ID.

    Returns an empty dict (and logs a warning) if the call fails, so the
    caller can still emit a partial inventory.
    """
    reports: dict[str, dict] = {}
    try:
        for page in client.paginate_get("admin/reports"):
            for r in page:
                reports[r["id"]] = r
        logger.info("Loaded %d reports from admin/reports.", len(reports))
    except Exception as exc:
        logger.warning("Failed to load admin/reports: %s. Enrichment will be partial.", exc)
    return reports


def get_all_groups(client: PowerBIClient) -> dict[str, dict]:
    """Load all workspaces via admin/groups ($top/$skip paging), keyed by workspace ID.

    admin/groups is rate-limited; the function sleeps briefly between pages and
    degrades gracefully on failure.
    """
    groups: dict[str, dict] = {}
    skip = 0

    while True:
        try:
            data = client.get(
                "admin/groups",
                params={"$top": str(_GROUPS_PAGE_SIZE), "$skip": str(skip)},
            )
            page = data.get("value", [])
            if not page:
                break
            for g in page:
                groups[g["id"]] = g
            skip += len(page)
            if len(page) < _GROUPS_PAGE_SIZE:
                break
            time.sleep(_GROUPS_INTER_PAGE_SLEEP)
        except Exception as exc:
            logger.warning(
                "Failed to load admin/groups at skip=%d: %s. Using %d workspaces loaded so far.",
                skip,
                exc,
                len(groups),
            )
            break

    logger.info("Loaded %d workspaces from admin/groups.", len(groups))
    return groups


def run_deep_scan(client: PowerBIClient, workspace_ids: list[str]) -> dict[str, dict]:
    """Run the metadata scanner and return scan results keyed by workspace ID.

    Prerequisites (tenant settings that must be enabled):
      - "Enhanced metadata scanning" (allows datasource and lineage detail)
      - "Allow service principals to use read-only Power BI admin APIs"

    Batches workspace IDs at 100 per request. Polls scanStatus until Succeeded.
    On any failure the batch is skipped and a warning is logged.
    """
    results: dict[str, dict] = {}

    for i in range(0, len(workspace_ids), _SCANNER_BATCH_SIZE):
        batch = workspace_ids[i : i + _SCANNER_BATCH_SIZE]
        logger.info(
            "Deep scan: submitting batch %d–%d (%d workspaces).",
            i + 1,
            i + len(batch),
            len(batch),
        )
        try:
            scan_response = client.post(
                "admin/workspaces/getInfo",
                json={
                    "workspaces": batch,
                    "datasetExpressions": False,
                    "datasetSchema": False,
                    "datasourceDetails": True,
                    "getArtifactUsers": False,
                    "lineage": True,
                },
            )
            scan_id: Optional[str] = scan_response.get("id")
            if not scan_id:
                logger.warning("No scan ID returned; skipping batch.")
                continue

            # Poll for completion.
            succeeded = False
            for poll in range(_SCANNER_MAX_POLLS):
                time.sleep(_SCANNER_POLL_INTERVAL)
                status_data = client.get(f"admin/workspaces/scanStatus/{scan_id}")
                status = status_data.get("status", "")
                logger.debug("Scan %s status: %s (poll %d)", scan_id, status, poll + 1)
                if status == "Succeeded":
                    succeeded = True
                    break
                if status in ("Failed", "Cancelled"):
                    logger.warning("Scan %s ended with status '%s'.", scan_id, status)
                    break

            if not succeeded:
                logger.warning("Scan %s did not complete in time; skipping batch.", scan_id)
                continue

            scan_result = client.get(f"admin/workspaces/scanResult/{scan_id}")
            for ws in scan_result.get("workspaces", []):
                results[ws["id"]] = ws

        except Exception as exc:
            logger.warning("Deep scan batch failed: %s. Skipping.", exc)

    logger.info("Deep scan complete. Results for %d workspaces.", len(results))
    return results


def detect_detailed_metadata_available(enriched: list[EnrichedReport]) -> bool:
    """Return True if the scanner returned any sensitivity label or datasource data.

    When "Enhanced metadata scanning" / "Detailed metadata responses" tenant
    settings are disabled, the scanner succeeds but all datasets come back with
    null labels and empty datasource lists. If no enriched report carries either
    piece of data we treat detailed metadata as unavailable and callers must
    suppress metadata-dependent flags to avoid false positives.

    Args:
        enriched: Reports after enrich_reports() has been applied.

    Returns:
        True if at least one report has a sensitivity label or datasource type.
    """
    return any(r.sensitivityLabel or r.datasetSourceTypes for r in enriched)


def enrich_reports(
    reports: list[PublishedReport],
    admin_reports: dict[str, dict],
    admin_groups: dict[str, dict],
    scan_results: Optional[dict[str, dict]] = None,
) -> list[EnrichedReport]:
    """Join published reports with admin report/workspace/scan data.

    Args:
        reports: Raw list from publishedToWeb.
        admin_reports: Dict from get_all_reports(), keyed by report ID.
        admin_groups: Dict from get_all_groups(), keyed by workspace ID.
        scan_results: Optional dict from run_deep_scan(), keyed by workspace ID.

    Returns:
        List of EnrichedReport with all available fields populated.
    """
    enriched: list[EnrichedReport] = []

    for report in reports:
        report_meta = admin_reports.get(report.artifactId, {})
        workspace_id: Optional[str] = report_meta.get("workspaceId")
        group_meta = admin_groups.get(workspace_id, {}) if workspace_id else {}

        # Determine enrichment quality.
        enrichment_status = "ok" if report_meta else "partial"

        # Deep scan: sensitivity label and datasource types.
        sensitivity_label: Optional[str] = None
        dataset_source_types: list[str] = []

        if scan_results and workspace_id:
            ws_scan = scan_results.get(workspace_id, {})
            dataset_id: Optional[str] = report_meta.get("datasetId")
            if dataset_id:
                for ds in ws_scan.get("datasets", []):
                    if ds.get("id") == dataset_id:
                        label_block = ds.get("sensitivityLabel") or {}
                        sensitivity_label = label_block.get("labelName") or label_block.get("name")
                        dataset_source_types = [
                            src.get("datasourceType", "")
                            for src in ds.get("datasourceUsages", [])
                            if src.get("datasourceType")
                        ]
                        break

        enriched.append(
            EnrichedReport(
                artifactId=report.artifactId,
                displayName=report.displayName,
                artifactType=report.artifactType,
                accessRight=report.accessRight,
                shareType=report.shareType,
                sharer=report.sharer,
                webUrl=report_meta.get("webUrl"),
                embedUrl=report_meta.get("embedUrl"),
                datasetId=report_meta.get("datasetId"),
                workspaceId=workspace_id,
                workspaceName=group_meta.get("name"),
                # Dataset name is not returned by admin/reports; available via deep scan only.
                datasetName=None,
                sensitivityLabel=sensitivity_label,
                datasetSourceTypes=dataset_source_types,
                enrichment_status=enrichment_status,
            )
        )

    return enriched
