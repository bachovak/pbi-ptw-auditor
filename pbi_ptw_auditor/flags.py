"""Heuristic risk flags applied per enriched report.

Each flag has a documented rationale. All flags are transparent (shown per row,
not aggregated into a score), toggleable via FlagConfig, and adjustable via
the CLI (--prod-workspace-regex, --no-flags).

Available flags
---------------
production_workspace
    The report lives in a workspace whose name matches a configurable
    case-insensitive regex (default: ``prod|production``). Publicly shared
    reports from production workspaces carry higher blast radius. Evaluated
    on every run regardless of deep-scan or metadata availability.

no_sensitivity_label
    The report's dataset has no Microsoft Purview / MIP sensitivity label.
    Without a label, automated DLP policies cannot act on this data path.
    Requires deep scan with detailed metadata responses enabled in the tenant.
    Marked **indeterminate** (not fired) when the tenant's enhanced metadata
    scanning settings are off.

sensitive_source
    The dataset is bound to a source type likely to contain sensitive or
    regulated data (e.g. SQL, DirectLake, Lakehouse). Configurable via
    FlagConfig.sensitive_source_types. Same metadata requirements as
    no_sensitivity_label; marked indeterminate when metadata is unavailable.

Indeterminate flags
-------------------
When deep scan runs but the tenant's "Enhanced metadata scanning" /
"Detailed metadata responses" settings are disabled, the scanner succeeds
but returns no label or datasource detail. In that case metadata-dependent
flags cannot be evaluated honestly. They are recorded in ``FlagResult.indeterminate``
rather than fired or silently skipped, so downstream consumers can distinguish
"genuinely no label" from "could not determine".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import EnrichedReport

# Canonical flag identifiers — use these as keys in output rows.
FLAG_PRODUCTION_WORKSPACE = "production_workspace"
FLAG_NO_SENSITIVITY_LABEL = "no_sensitivity_label"
FLAG_SENSITIVE_SOURCE = "sensitive_source"


@dataclass
class FlagResult:
    """Outcome of evaluating flags for a single report.

    Attributes:
        fired: Flags that positively fired (conditions met).
        indeterminate: Flags that could not be evaluated due to unavailable
            metadata. These must not be treated as fired or as clear.
    """

    fired: list[str] = field(default_factory=list)
    indeterminate: list[str] = field(default_factory=list)


@dataclass
class FlagConfig:
    """Configuration knobs for every heuristic flag.

    All values can be overridden at the CLI level so teams can tune the
    rules to their naming conventions and data architecture without editing
    source code.
    """

    # Regex applied case-insensitively to workspaceName.
    production_workspace_regex: str = r"prod|production"

    # Datasource types that trigger the sensitive_source flag.
    # Values must match the ``datasourceType`` strings returned by the
    # metadata scanner API (case-insensitive comparison is applied).
    sensitive_source_types: list[str] = field(
        default_factory=lambda: [
            "Sql",
            "DirectLake",
            "Lakehouse",
            "AzureSqlDatabase",
            "AzureSqlDatabaseDataWarehouse",
            "AnalysisServices",
            "SharePointList",
            "OData",
        ]
    )

    enable_production_workspace: bool = True
    enable_no_sensitivity_label: bool = True
    enable_sensitive_source: bool = True


def apply_flags(
    report: EnrichedReport,
    config: FlagConfig,
    *,
    deep_scan: bool = False,
    detailed_metadata_available: bool = True,
) -> FlagResult:
    """Evaluate heuristic flags for a single enriched report.

    Args:
        report: The enriched report to evaluate.
        config: Flag configuration (regexes, watchlists, enable toggles).
        deep_scan: Whether the run included the metadata scanner. Metadata-
            dependent flags are skipped when False.
        detailed_metadata_available: Whether the scanner returned actual label
            and datasource data. When False (tenant settings not enabled),
            metadata-dependent flags are marked indeterminate rather than fired,
            to avoid false positives.

    Returns:
        FlagResult with ``fired`` (conditions met) and ``indeterminate``
        (could not be evaluated) flag lists, both sorted.
    """
    fired: list[str] = []
    indeterminate: list[str] = []

    # production_workspace: always evaluatable — no scanner data required.
    if config.enable_production_workspace and report.workspaceName:
        try:
            pattern = re.compile(config.production_workspace_regex, re.IGNORECASE)
            if pattern.search(report.workspaceName):
                fired.append(FLAG_PRODUCTION_WORKSPACE)
        except re.error:
            # Malformed regex — skip silently so the rest of the run continues.
            pass

    if deep_scan:
        if not detailed_metadata_available:
            # Scanner ran but the tenant's enhanced metadata scanning settings
            # are disabled — labels and source types are absent for all datasets.
            # Mark metadata flags as indeterminate rather than firing on empty data.
            if config.enable_no_sensitivity_label:
                indeterminate.append(FLAG_NO_SENSITIVITY_LABEL)
            if config.enable_sensitive_source:
                indeterminate.append(FLAG_SENSITIVE_SOURCE)
        else:
            if config.enable_no_sensitivity_label and not report.sensitivityLabel:
                fired.append(FLAG_NO_SENSITIVITY_LABEL)

            if config.enable_sensitive_source and report.datasetSourceTypes:
                watchlist = {s.lower() for s in config.sensitive_source_types}
                if any(src.lower() in watchlist for src in report.datasetSourceTypes):
                    fired.append(FLAG_SENSITIVE_SOURCE)

    return FlagResult(fired=sorted(fired), indeterminate=sorted(indeterminate))
