"""Command-line entry point for pbi-ptw-auditor."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from dotenv import load_dotenv

from .api_client import PowerBIClient
from .auth import get_token_device_code, get_token_service_principal
from .enrich import enrich_reports, get_all_groups, get_all_reports, run_deep_scan
from .flags import FlagConfig, apply_flags
from .models import RunMetadata
from .reporters.csv_reporter import write_csv
from .reporters.html_reporter import write_html
from .reporters.json_reporter import write_json

load_dotenv()


@click.command()
@click.option(
    "--auth",
    type=click.Choice(["service-principal", "device-code"]),
    default="service-principal",
    show_default=True,
    help=(
        "Authentication method. 'service-principal' uses client-credentials flow "
        "(requires PBI_TENANT_ID, PBI_CLIENT_ID, PBI_CLIENT_SECRET). "
        "'device-code' is interactive (requires PBI_TENANT_ID, PBI_CLIENT_ID)."
    ),
)
@click.option(
    "--deep-scan",
    is_flag=True,
    default=False,
    help=(
        "Enable the metadata scanner for sensitivity labels and datasource types. "
        "Requires 'Enhanced metadata scanning' tenant settings to be enabled. Slow and rate-limited."
    ),
)
@click.option(
    "--output-dir",
    default="./output",
    show_default=True,
    help="Directory to write output files into.",
)
@click.option(
    "--formats",
    default="csv,json,html",
    show_default=True,
    help="Comma-separated list of output formats: csv, json, html.",
)
@click.option(
    "--no-flags",
    is_flag=True,
    default=False,
    help="Disable all risk flag evaluation. Flags column will be empty.",
)
@click.option(
    "--redact",
    is_flag=True,
    default=False,
    help="Mask sharer email addresses in all outputs (e.g. j****@contoso.com).",
)
@click.option(
    "--prod-workspace-regex",
    default="prod|production",
    show_default=True,
    help="Case-insensitive regex to flag reports in production workspaces.",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    show_default=True,
    help="Logging verbosity.",
)
def main(
    auth: str,
    deep_scan: bool,
    output_dir: str,
    formats: str,
    no_flags: bool,
    redact: bool,
    prod_workspace_regex: str,
    log_level: str,
) -> None:
    """Inventory every Power BI report published to the open web in your tenant.

    Reads tenant credentials from environment variables (or a .env file).
    Produces CSV, JSON, and HTML reports in the output directory.

    \b
    Examples:
      # Service principal, all formats, default output directory:
      pbi-ptw-auditor --auth service-principal

    \b
      # Interactive login, deep scan enabled, emails redacted, CSV only:
      pbi-ptw-auditor --auth device-code --deep-scan --redact --formats csv

    \b
      # Custom production workspace regex, JSON only, verbose logging:
      pbi-ptw-auditor --prod-workspace-regex "prod|prd|live" --formats json --log-level DEBUG
    """
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logger = logging.getLogger("pbi_ptw_auditor")

    # ── Validate config ───────────────────────────────────────────────────────
    tenant_id = os.environ.get("PBI_TENANT_ID", "").strip()
    client_id = os.environ.get("PBI_CLIENT_ID", "").strip()

    if not tenant_id or not client_id:
        click.echo(
            "Error: PBI_TENANT_ID and PBI_CLIENT_ID must be set in the environment or .env file.",
            err=True,
        )
        sys.exit(1)

    selected_formats = [f.strip().lower() for f in formats.split(",") if f.strip()]
    unknown = set(selected_formats) - {"csv", "json", "html"}
    if unknown:
        click.echo(f"Error: unknown format(s): {', '.join(sorted(unknown))}", err=True)
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Authenticate ──────────────────────────────────────────────────────────
    try:
        if auth == "service-principal":
            client_secret = os.environ.get("PBI_CLIENT_SECRET", "").strip()
            if not client_secret:
                click.echo("Error: PBI_CLIENT_SECRET must be set for service-principal auth.", err=True)
                sys.exit(1)
            token = get_token_service_principal(tenant_id, client_id, client_secret)
        else:
            token = get_token_device_code(tenant_id, client_id)
    except Exception as exc:
        click.echo(f"Authentication error: {exc}", err=True)
        sys.exit(1)

    # ── Retrieve + enrich ─────────────────────────────────────────────────────
    with PowerBIClient(token) as client:
        from .retrieve import get_published_to_web

        logger.info("Retrieving reports published to web…")
        raw_reports = get_published_to_web(client)
        click.echo(f"Found {len(raw_reports)} report(s) published to the open web.")

        logger.info("Loading admin/reports for enrichment…")
        admin_reports = get_all_reports(client)

        logger.info("Loading admin/groups for enrichment…")
        admin_groups = get_all_groups(client)

        scan_results = None
        if deep_scan:
            workspace_ids = list(
                {r.get("workspaceId") for r in admin_reports.values() if r.get("workspaceId")}
            )
            logger.info("Running deep scan on %d workspace(s)…", len(workspace_ids))
            scan_results = run_deep_scan(client, workspace_ids)

        enriched = enrich_reports(raw_reports, admin_reports, admin_groups, scan_results)

    # ── Apply flags ───────────────────────────────────────────────────────────
    if not no_flags:
        flag_config = FlagConfig(production_workspace_regex=prod_workspace_regex)
        for report in enriched:
            report.flags = apply_flags(report, flag_config, deep_scan=deep_scan)

    # ── Build run metadata ────────────────────────────────────────────────────
    flagged_count = sum(1 for r in enriched if r.flags)
    missing_label_count = sum(1 for r in enriched if deep_scan and not r.sensitivityLabel)

    metadata = RunMetadata(
        utc_timestamp=datetime.now(timezone.utc),
        tenant_id=tenant_id,
        auth_method=auth,
        deep_scan=deep_scan,
        total_count=len(enriched),
        flagged_count=flagged_count,
        missing_label_count=missing_label_count,
    )

    ts = metadata.utc_timestamp.strftime("%Y%m%d_%H%M%S")

    # ── Write outputs ─────────────────────────────────────────────────────────
    if "csv" in selected_formats:
        path = output_path / f"ptw_audit_{ts}.csv"
        write_csv(enriched, path, redact=redact)
        click.echo(f"CSV  → {path}")

    if "json" in selected_formats:
        path = output_path / f"ptw_audit_{ts}.json"
        write_json(enriched, metadata, path, redact=redact)
        click.echo(f"JSON → {path}")

    if "html" in selected_formats:
        path = output_path / f"ptw_audit_{ts}.html"
        write_html(enriched, metadata, path, redact=redact)
        click.echo(f"HTML → {path}")

    click.echo(
        f"\nAudit complete: {metadata.total_count} public report(s), "
        f"{metadata.flagged_count} flagged."
    )


if __name__ == "__main__":
    main()
