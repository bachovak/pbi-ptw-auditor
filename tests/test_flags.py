"""Tests for the heuristic flag rules in pbi_ptw_auditor.flags."""

from __future__ import annotations

from pbi_ptw_auditor.flags import (
    FLAG_NO_SENSITIVITY_LABEL,
    FLAG_PRODUCTION_WORKSPACE,
    FLAG_SENSITIVE_SOURCE,
    FlagConfig,
    FlagResult,
    apply_flags,
)
from pbi_ptw_auditor.models import EnrichedReport, Sharer

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_report(**kwargs) -> EnrichedReport:
    defaults = dict(
        artifactId="report-1",
        displayName="Sales Report",
        sharer=Sharer(displayName="Alice", identifier="alice-id", principalType="User"),
        workspaceName=None,
        sensitivityLabel=None,
        datasetSourceTypes=[],
    )
    defaults.update(kwargs)
    return EnrichedReport(**defaults)


_DEFAULT_CONFIG = FlagConfig()


# ── production_workspace ───────────────────────────────────────────────────────


def test_production_workspace_flag_fires_on_prod() -> None:
    report = _make_report(workspaceName="Sales - Production")
    assert FLAG_PRODUCTION_WORKSPACE in apply_flags(report, _DEFAULT_CONFIG).fired


def test_production_workspace_flag_fires_on_prod_lowercase() -> None:
    report = _make_report(workspaceName="analytics_prod")
    assert FLAG_PRODUCTION_WORKSPACE in apply_flags(report, _DEFAULT_CONFIG).fired


def test_production_workspace_flag_does_not_fire_for_dev() -> None:
    report = _make_report(workspaceName="Sales - Dev")
    assert FLAG_PRODUCTION_WORKSPACE not in apply_flags(report, _DEFAULT_CONFIG).fired


def test_production_workspace_flag_does_not_fire_when_name_is_none() -> None:
    report = _make_report(workspaceName=None)
    assert FLAG_PRODUCTION_WORKSPACE not in apply_flags(report, _DEFAULT_CONFIG).fired


def test_production_workspace_custom_regex() -> None:
    config = FlagConfig(production_workspace_regex=r"live|prd")
    report = _make_report(workspaceName="Finance-Live")
    assert FLAG_PRODUCTION_WORKSPACE in apply_flags(report, config).fired


def test_production_workspace_disabled() -> None:
    config = FlagConfig(enable_production_workspace=False)
    report = _make_report(workspaceName="Production Finance")
    assert FLAG_PRODUCTION_WORKSPACE not in apply_flags(report, config).fired


def test_malformed_regex_does_not_crash() -> None:
    config = FlagConfig(production_workspace_regex="[invalid(")
    report = _make_report(workspaceName="Production Finance")
    result = apply_flags(report, config)
    assert FLAG_PRODUCTION_WORKSPACE not in result.fired


# ── no_sensitivity_label ───────────────────────────────────────────────────────


def test_no_label_flag_fires_when_deep_scan_and_no_label() -> None:
    report = _make_report(sensitivityLabel=None)
    assert FLAG_NO_SENSITIVITY_LABEL in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_no_label_flag_does_not_fire_when_label_present() -> None:
    report = _make_report(sensitivityLabel="Confidential")
    assert FLAG_NO_SENSITIVITY_LABEL not in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_no_label_flag_does_not_fire_without_deep_scan() -> None:
    """When deep_scan=False, missing label must not be flagged (data unavailable)."""
    report = _make_report(sensitivityLabel=None)
    result = apply_flags(report, _DEFAULT_CONFIG, deep_scan=False)
    assert FLAG_NO_SENSITIVITY_LABEL not in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL not in result.indeterminate


def test_no_label_flag_disabled() -> None:
    config = FlagConfig(enable_no_sensitivity_label=False)
    report = _make_report(sensitivityLabel=None)
    result = apply_flags(report, config, deep_scan=True, detailed_metadata_available=True)
    assert FLAG_NO_SENSITIVITY_LABEL not in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL not in result.indeterminate


def test_no_label_flag_indeterminate_when_metadata_unavailable() -> None:
    """When detailed metadata is unavailable, no_sensitivity_label is indeterminate, not fired."""
    report = _make_report(sensitivityLabel=None)
    result = apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=False
    )
    assert FLAG_NO_SENSITIVITY_LABEL not in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL in result.indeterminate


# ── sensitive_source ───────────────────────────────────────────────────────────


def test_sensitive_source_flag_fires_for_sql() -> None:
    report = _make_report(datasetSourceTypes=["Sql"])
    assert FLAG_SENSITIVE_SOURCE in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_sensitive_source_flag_fires_case_insensitive() -> None:
    report = _make_report(datasetSourceTypes=["sql"])
    assert FLAG_SENSITIVE_SOURCE in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_sensitive_source_flag_fires_for_direct_lake() -> None:
    report = _make_report(datasetSourceTypes=["DirectLake"])
    assert FLAG_SENSITIVE_SOURCE in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_sensitive_source_flag_does_not_fire_for_excel() -> None:
    report = _make_report(datasetSourceTypes=["Excel"])
    assert FLAG_SENSITIVE_SOURCE not in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_sensitive_source_flag_does_not_fire_without_deep_scan() -> None:
    report = _make_report(datasetSourceTypes=["Sql"])
    result = apply_flags(report, _DEFAULT_CONFIG, deep_scan=False)
    assert FLAG_SENSITIVE_SOURCE not in result.fired
    assert FLAG_SENSITIVE_SOURCE not in result.indeterminate


def test_sensitive_source_flag_does_not_fire_when_empty() -> None:
    report = _make_report(datasetSourceTypes=[])
    assert FLAG_SENSITIVE_SOURCE not in apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_sensitive_source_custom_watchlist() -> None:
    config = FlagConfig(sensitive_source_types=["Excel", "CSV"])
    report = _make_report(datasetSourceTypes=["Excel"])
    assert FLAG_SENSITIVE_SOURCE in apply_flags(
        report, config, deep_scan=True, detailed_metadata_available=True
    ).fired


def test_sensitive_source_disabled() -> None:
    config = FlagConfig(enable_sensitive_source=False)
    report = _make_report(datasetSourceTypes=["Sql"])
    result = apply_flags(report, config, deep_scan=True, detailed_metadata_available=True)
    assert FLAG_SENSITIVE_SOURCE not in result.fired
    assert FLAG_SENSITIVE_SOURCE not in result.indeterminate


def test_sensitive_source_indeterminate_when_metadata_unavailable() -> None:
    """When detailed metadata is unavailable, sensitive_source is indeterminate, not fired."""
    report = _make_report(datasetSourceTypes=["Sql"])
    result = apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=False
    )
    assert FLAG_SENSITIVE_SOURCE not in result.fired
    assert FLAG_SENSITIVE_SOURCE in result.indeterminate


# ── Combined / ordering ────────────────────────────────────────────────────────


def test_multiple_flags_fire_together() -> None:
    report = _make_report(
        workspaceName="Production Finance",
        sensitivityLabel=None,
        datasetSourceTypes=["Sql"],
    )
    result = apply_flags(report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True)
    assert FLAG_PRODUCTION_WORKSPACE in result.fired
    assert FLAG_NO_SENSITIVITY_LABEL in result.fired
    assert FLAG_SENSITIVE_SOURCE in result.fired


def test_flags_are_sorted() -> None:
    report = _make_report(
        workspaceName="prod",
        sensitivityLabel=None,
        datasetSourceTypes=["Sql"],
    )
    result = apply_flags(report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True)
    assert result.fired == sorted(result.fired)


def test_indeterminate_flags_are_sorted() -> None:
    report = _make_report(workspaceName="prod")
    result = apply_flags(report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=False)
    assert result.indeterminate == sorted(result.indeterminate)


def test_no_flags_on_clean_report() -> None:
    report = _make_report(
        workspaceName="Finance - Dev",
        sensitivityLabel="Public",
        datasetSourceTypes=["Excel"],
    )
    result = apply_flags(report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=True)
    assert result.fired == []
    assert result.indeterminate == []


def test_production_workspace_fires_even_when_metadata_unavailable() -> None:
    """production_workspace is not metadata-dependent and must still fire."""
    report = _make_report(workspaceName="Production Finance")
    result = apply_flags(
        report, _DEFAULT_CONFIG, deep_scan=True, detailed_metadata_available=False
    )
    assert FLAG_PRODUCTION_WORKSPACE in result.fired


def test_apply_flags_returns_flag_result() -> None:
    report = _make_report()
    result = apply_flags(report, _DEFAULT_CONFIG)
    assert isinstance(result, FlagResult)
    assert isinstance(result.fired, list)
    assert isinstance(result.indeterminate, list)
