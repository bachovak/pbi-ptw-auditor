"""Pydantic models for the Power BI Publish-to-Web audit tool."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Sharer(BaseModel):
    """The Power BI user or service principal who created the embed code."""

    displayName: str
    emailAddress: Optional[str] = None
    identifier: str
    graphId: Optional[str] = None
    principalType: str  # User | Group | ServicePrincipal | App


class PublishedReport(BaseModel):
    """Raw payload from admin/widelySharedArtifacts/publishedToWeb."""

    artifactId: str
    displayName: str
    artifactType: str = "Report"
    accessRight: Optional[str] = None
    shareType: str = "PublishToWeb"
    sharer: Sharer


class EnrichedReport(BaseModel):
    """PublishedReport joined with admin/reports and admin/groups data."""

    # Core identity
    artifactId: str
    displayName: str
    artifactType: str = "Report"
    accessRight: Optional[str] = None
    shareType: str = "PublishToWeb"
    sharer: Sharer

    # Medium enrichment (admin/reports + admin/groups)
    webUrl: Optional[str] = None
    embedUrl: Optional[str] = None
    datasetId: Optional[str] = None
    workspaceId: Optional[str] = None
    workspaceName: Optional[str] = None
    datasetName: Optional[str] = None

    # Rich enrichment (metadata scanner)
    sensitivityLabel: Optional[str] = None
    datasetSourceTypes: list[str] = Field(default_factory=list)

    # Audit metadata
    flags: list[str] = Field(default_factory=list)
    indeterminate_flags: list[str] = Field(default_factory=list)
    # not_requested | available | indeterminate
    metadata_status: str = "not_requested"
    enrichment_status: str = "ok"  # ok | partial | failed


class RunMetadata(BaseModel):
    """Contextual metadata written to the JSON report header."""

    utc_timestamp: datetime
    tenant_id: str
    auth_method: str
    deep_scan: bool
    total_count: int
    flagged_count: int
    # None means the count could not be determined (metadata unavailable).
    missing_label_count: Optional[int] = None
    detailed_metadata_available: bool = True
    warnings: list[str] = Field(default_factory=list)
