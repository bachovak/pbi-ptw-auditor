"""Retrieve all reports currently published to the open web."""

from __future__ import annotations

import logging

from .api_client import PowerBIClient
from .models import PublishedReport, Sharer

logger = logging.getLogger(__name__)

_PUBLISHED_TO_WEB_PATH = "admin/widelySharedArtifacts/publishedToWeb"

# Sibling path for future expansion — listed here so it is never accidentally called.
# _LINKS_SHARED_TO_ORG_PATH = "admin/widelySharedArtifacts/linksSharedToWholeOrganization"


def get_published_to_web(client: PowerBIClient) -> list[PublishedReport]:
    """Fetch every report whose embed code has been published to the open internet.

    Uses continuationToken pagination; never follows continuationUri (which the
    API can point at the sibling linksSharedToWholeOrganization endpoint).

    Args:
        client: Authenticated PowerBIClient instance.

    Returns:
        List of PublishedReport objects.
    """
    reports: list[PublishedReport] = []
    page_num = 0

    for page in client.paginate_get(_PUBLISHED_TO_WEB_PATH):
        page_num += 1
        logger.info("Page %d: received %d item(s).", page_num, len(page))

        for item in page:
            sharer_raw = item.get("sharer") or {}
            sharer = Sharer(
                displayName=sharer_raw.get("displayName") or "",
                emailAddress=sharer_raw.get("emailAddress"),
                identifier=sharer_raw.get("identifier") or "",
                graphId=sharer_raw.get("graphId"),
                principalType=sharer_raw.get("principalType") or "Unknown",
            )
            reports.append(
                PublishedReport(
                    artifactId=item["artifactId"],
                    displayName=item.get("displayName") or "",
                    artifactType=item.get("artifactType") or "Report",
                    accessRight=item.get("accessRight"),
                    shareType=item.get("shareType") or "PublishToWeb",
                    sharer=sharer,
                )
            )

    logger.info("Total reports published to web: %d", len(reports))
    return reports
