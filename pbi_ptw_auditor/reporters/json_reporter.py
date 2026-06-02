"""JSON reporter: structured output with run_metadata header."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import EnrichedReport, RunMetadata
from ..utils import redact_email as _redact


def _report_to_dict(r: EnrichedReport, *, redact: bool) -> dict[str, Any]:
    email = r.sharer.emailAddress or ""
    if redact:
        email = _redact(email)
    return {
        "artifactId": r.artifactId,
        "displayName": r.displayName,
        "artifactType": r.artifactType,
        "shareType": r.shareType,
        "accessRight": r.accessRight,
        "workspaceId": r.workspaceId,
        "workspaceName": r.workspaceName,
        "datasetId": r.datasetId,
        "datasetName": r.datasetName,
        "webUrl": r.webUrl,
        "embedUrl": r.embedUrl,
        "sharer": {
            "displayName": r.sharer.displayName,
            "emailAddress": email,
            "identifier": r.sharer.identifier,
            "principalType": r.sharer.principalType,
        },
        "sensitivityLabel": r.sensitivityLabel,
        "datasetSourceTypes": r.datasetSourceTypes,
        "flags": r.flags,
        "indeterminate_flags": r.indeterminate_flags,
        "metadata_status": r.metadata_status,
        "enrichment_status": r.enrichment_status,
    }


def write_json(
    reports: list[EnrichedReport],
    metadata: RunMetadata,
    path: Path,
    *,
    redact: bool = False,
) -> None:
    """Write enriched reports and run metadata to a JSON file.

    Args:
        reports: List of enriched reports.
        metadata: Run-level metadata written to the ``run_metadata`` block.
        path: Destination file path.
        redact: If True, mask sharer email addresses.
    """
    output = {
        "run_metadata": {
            "utc_timestamp": metadata.utc_timestamp.isoformat(),
            "tenant_id": metadata.tenant_id,
            "auth_method": metadata.auth_method,
            "deep_scan": metadata.deep_scan,
            "detailed_metadata_available": metadata.detailed_metadata_available,
            "total_count": metadata.total_count,
            "flagged_count": metadata.flagged_count,
            # null when detailed_metadata_available is False (could not be determined).
            "missing_label_count": metadata.missing_label_count,
            "warnings": metadata.warnings,
        },
        "reports": [_report_to_dict(r, redact=redact) for r in reports],
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
