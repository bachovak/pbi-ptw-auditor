"""Heuristic risk flags applied per enriched report.

Each flag has a documented rationale. All flags are transparent (shown per row,
not aggregated into a score), toggleable via FlagConfig, and adjustable via
the CLI (--prod-workspace-regex, --no-flags).

Available flags
---------------
production_workspace
    The report lives in a workspace whose name matches a configurable
    case-insensitive regex (default: ``prod|production``). Publicly shared
    reports from production workspaces carry higher blast radius.

no_sensitivity_label
    (Deep scan only) The report's dataset has no Microsoft Purview / MIP
    sensitivity label. Without a label, automated DLP policies cannot act
    on this data path.

sensitive_source
    (Deep scan only) The dataset is bound to a source type that is likely
    to contain sensitive or regulated data (e.g. SQL, DirectLake, Lakehouse).
    Configurable via FlagConfig.sensitive_source_types.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import EnrichedReport

# Canonical flag identifiers (use these as keys in output rows).
FLAG_PRODUCTION_WORKSPACE = "production_workspace"
FLAG_NO_SENSITIVITY_LABEL = "no_sensitivity_label"
FLAG_SENSITIVE_SOURCE = "sensitive_source"


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
) -> list[str]:
    """Evaluate heuristic flags for a single enriched report.

    Args:
        report: The enriched report to evaluate.
        config: Flag configuration (regexes, watchlists, enable toggles).
        deep_scan: Whether the run included the metadata scanner. Flags that
            depend on scanner data are skipped when False to avoid false
            negatives from missing data.

    Returns:
        Sorted list of flag identifier strings that fired.
    """
    fired: list[str] = []

    if config.enable_production_workspace and report.workspaceName:
        try:
            pattern = re.compile(config.production_workspace_regex, re.IGNORECASE)
            if pattern.search(report.workspaceName):
                fired.append(FLAG_PRODUCTION_WORKSPACE)
        except re.error:
            # Malformed regex — skip silently so the rest of the run continues.
            pass

    if deep_scan:
        if config.enable_no_sensitivity_label and not report.sensitivityLabel:
            fired.append(FLAG_NO_SENSITIVITY_LABEL)

        if config.enable_sensitive_source and report.datasetSourceTypes:
            watchlist = {s.lower() for s in config.sensitive_source_types}
            if any(src.lower() in watchlist for src in report.datasetSourceTypes):
                fired.append(FLAG_SENSITIVE_SOURCE)

    return sorted(fired)
