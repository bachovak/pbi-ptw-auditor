"""HTML reporter: self-contained single-file report with sortable/filterable table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..models import EnrichedReport, RunMetadata
from ..utils import redact_email as _redact

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def write_html(
    reports: list[EnrichedReport],
    metadata: RunMetadata,
    path: Path,
    *,
    redact: bool = False,
) -> None:
    """Render and write the HTML audit report.

    Args:
        reports: List of enriched reports.
        metadata: Run-level metadata for the summary cards.
        path: Destination file path.
        redact: If True, mask sharer email addresses.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html.j2")

    report_dicts: list[dict[str, Any]] = []
    for r in reports:
        email = r.sharer.emailAddress or ""
        if redact:
            email = _redact(email)
        report_dicts.append(
            {
                "artifactId": r.artifactId,
                "displayName": r.displayName,
                "workspaceId": r.workspaceId or "",
                "workspaceName": r.workspaceName or "",
                "datasetId": r.datasetId or "",
                "webUrl": r.webUrl or "",
                "embedUrl": r.embedUrl or "",
                "sharerName": r.sharer.displayName,
                "sharerEmail": email,
                "sharerPrincipalType": r.sharer.principalType,
                "sensitivityLabel": r.sensitivityLabel or "",
                "datasetSourceTypes": "|".join(r.datasetSourceTypes),
                "flags": r.flags,
                "enrichment_status": r.enrichment_status,
            }
        )

    distinct_sharers = len({r.sharer.identifier for r in reports})
    distinct_workspaces = len({r.workspaceId for r in reports if r.workspaceId})

    html = template.render(
        metadata={
            "utc_timestamp": metadata.utc_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "tenant_id": metadata.tenant_id,
            "auth_method": metadata.auth_method,
            "deep_scan": metadata.deep_scan,
            "total_count": metadata.total_count,
            "flagged_count": metadata.flagged_count,
            "missing_label_count": metadata.missing_label_count,
        },
        reports=report_dicts,
        distinct_sharers=distinct_sharers,
        distinct_workspaces=distinct_workspaces,
    )

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
