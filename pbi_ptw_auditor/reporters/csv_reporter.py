"""CSV reporter: one flat row per published report."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import EnrichedReport
from ..utils import redact_email as _redact

_FIELDNAMES = [
    "artifactId",
    "displayName",
    "artifactType",
    "shareType",
    "accessRight",
    "workspaceId",
    "workspaceName",
    "datasetId",
    "datasetName",
    "webUrl",
    "embedUrl",
    "sharerName",
    "sharerEmail",
    "sharerPrincipalType",
    "sensitivityLabel",
    "datasetSourceTypes",
    "flags",
    "enrichment_status",
]


def write_csv(reports: list[EnrichedReport], path: Path, *, redact: bool = False) -> None:
    """Write enriched reports to a CSV file.

    Args:
        reports: List of enriched reports.
        path: Destination file path.
        redact: If True, mask sharer email addresses.
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        writer.writeheader()

        for r in reports:
            email = r.sharer.emailAddress or ""
            if redact:
                email = _redact(email)

            writer.writerow(
                {
                    "artifactId": r.artifactId,
                    "displayName": r.displayName,
                    "artifactType": r.artifactType,
                    "shareType": r.shareType,
                    "accessRight": r.accessRight or "",
                    "workspaceId": r.workspaceId or "",
                    "workspaceName": r.workspaceName or "",
                    "datasetId": r.datasetId or "",
                    "datasetName": r.datasetName or "",
                    "webUrl": r.webUrl or "",
                    "embedUrl": r.embedUrl or "",
                    "sharerName": r.sharer.displayName,
                    "sharerEmail": email,
                    "sharerPrincipalType": r.sharer.principalType,
                    "sensitivityLabel": r.sensitivityLabel or "",
                    "datasetSourceTypes": "|".join(r.datasetSourceTypes),
                    "flags": "|".join(r.flags),
                    "enrichment_status": r.enrichment_status,
                }
            )
