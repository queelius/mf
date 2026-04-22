"""
Series audit: read-only health checks for series and their source repos.

Detects drift like missing nav entries, orphaned sync state, broken
links to non-existent posts, and stale syncs. Reports findings without
modifying anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from mf.core.config import get_paths
from mf.core.database import SeriesDatabase, SeriesEntry

console = Console()

STALE_DAYS = 30


@dataclass
class AuditFinding:
    """A single audit finding for a series."""

    severity: str  # "error", "warn", "info"
    category: str  # "nav", "sync", "source", "structure"
    series: str
    message: str
    detail: str = ""


@dataclass
class SeriesAuditReport:
    """Audit report for a single series."""

    series: str
    findings: list[AuditFinding] = field(default_factory=list)

    def add(self, severity: str, category: str, message: str, detail: str = "") -> None:
        self.findings.append(
            AuditFinding(severity=severity, category=category,
                         series=self.series, message=message, detail=detail)
        )

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")

    @property
    def is_clean(self) -> bool:
        return self.errors == 0 and self.warnings == 0


def _resolve_path(path_str: str) -> Path:
    """Expand ~/ in a path string to an absolute Path."""
    return Path(path_str.replace("~", str(Path.home())))


def _read_mkdocs_nav_posts(mkdocs_yml: Path) -> set[str]:
    """Extract post slugs referenced in mkdocs.yml nav.

    Looks for any path matching ``post/<slug>/index.md`` anywhere in the
    YAML file (handles deeply nested nav structures without parsing).
    """
    if not mkdocs_yml.exists():
        return set()
    text = mkdocs_yml.read_text(encoding="utf-8")
    return set(re.findall(r"post/([^/\s]+)/index\.md", text))


def _read_disk_posts(post_dir: Path) -> set[str]:
    """List post slugs on disk (subdirs of post_dir containing index.md)."""
    if not post_dir.is_dir():
        return set()
    return {
        p.name
        for p in post_dir.iterdir()
        if p.is_dir() and (p / "index.md").exists()
    }


def audit_nav(entry: SeriesEntry, source_dir: Path) -> list[AuditFinding]:
    """Check mkdocs nav drift against post directory.

    Returns findings for:
    - Posts on disk but not in nav (unreachable from sidebar)
    - Posts in nav but missing from disk (broken nav links)
    """
    findings: list[AuditFinding] = []
    mkdocs_yml = source_dir / "mkdocs.yml"
    if not mkdocs_yml.exists():
        return findings  # nothing to audit; not all series use mkdocs

    posts_subdir = entry.posts_subdir or "post"
    post_dir = source_dir / posts_subdir
    disk = _read_disk_posts(post_dir)
    nav = _read_mkdocs_nav_posts(mkdocs_yml)

    for slug in sorted(disk - nav):
        findings.append(AuditFinding(
            severity="warn",
            category="nav",
            series=entry.slug,
            message=f"post not in mkdocs nav: {slug}",
            detail="post is reachable by direct URL but missing from sidebar",
        ))
    for slug in sorted(nav - disk):
        findings.append(AuditFinding(
            severity="error",
            category="nav",
            series=entry.slug,
            message=f"mkdocs nav references missing post: {slug}",
            detail="nav link will 404",
        ))
    return findings


def audit_source(entry: SeriesEntry, source_dir: Path) -> list[AuditFinding]:
    """Check that the configured source_dir is usable."""
    findings: list[AuditFinding] = []
    if not source_dir.exists():
        findings.append(AuditFinding(
            severity="error",
            category="source",
            series=entry.slug,
            message=f"source_dir does not exist: {source_dir}",
        ))
        return findings
    if not source_dir.is_dir():
        findings.append(AuditFinding(
            severity="error",
            category="source",
            series=entry.slug,
            message=f"source_dir is not a directory: {source_dir}",
        ))
        return findings
    posts_subdir = entry.posts_subdir or "post"
    post_dir = source_dir / posts_subdir
    if not post_dir.exists():
        findings.append(AuditFinding(
            severity="warn",
            category="source",
            series=entry.slug,
            message=f"posts subdir missing: {post_dir.relative_to(source_dir)}",
        ))
    landing = entry.landing_page
    if landing:
        landing_path = source_dir / landing
        if not landing_path.exists():
            findings.append(AuditFinding(
                severity="warn",
                category="source",
                series=entry.slug,
                message=f"landing_page missing in source: {landing}",
            ))
    return findings


def audit_sync_state(entry: SeriesEntry, source_dir: Path) -> list[AuditFinding]:
    """Check sync state for orphans and staleness."""
    findings: list[AuditFinding] = []
    posts_subdir = entry.posts_subdir or "post"
    post_dir = source_dir / posts_subdir
    disk = _read_disk_posts(post_dir) if post_dir.is_dir() else set()
    paths = get_paths()
    blog_post_dir = paths.posts

    sync_state = entry.sync_state

    cutoff = datetime.now() - timedelta(days=STALE_DAYS)
    stale_count = 0

    for slug, state in sync_state.items():
        if slug.startswith("_"):
            continue
        # Orphan: in sync state but neither side has the file
        in_source = slug in disk
        in_blog = (blog_post_dir / slug / "index.md").exists()
        if not in_source and not in_blog:
            findings.append(AuditFinding(
                severity="warn",
                category="sync",
                series=entry.slug,
                message=f"orphan sync state: {slug}",
                detail="post missing from both source and blog; clean from _sync_state",
            ))
            continue
        # Staleness check
        last_synced_str = state.get("last_synced", "")
        if last_synced_str:
            try:
                last_synced = datetime.fromisoformat(last_synced_str)
                if last_synced < cutoff:
                    stale_count += 1
            except ValueError:
                pass

    if stale_count:
        findings.append(AuditFinding(
            severity="info",
            category="sync",
            series=entry.slug,
            message=f"{stale_count} post(s) not synced in >{STALE_DAYS} days",
            detail="run `mf series sync <slug>` to refresh",
        ))
    return findings


def audit_series(entry: SeriesEntry) -> SeriesAuditReport:
    """Run all audits for a single series."""
    report = SeriesAuditReport(series=entry.slug)
    if not entry.source_dir:
        report.add("info", "structure", "no source_dir configured (local-only series)")
        return report

    # entry.source_dir is already a resolved Path
    source_dir = entry.source_dir
    for f in audit_source(entry, source_dir):
        report.findings.append(f)
    # Skip nav and sync audits if source itself is missing
    if any(f.severity == "error" and f.category == "source" for f in report.findings):
        return report
    for f in audit_nav(entry, source_dir):
        report.findings.append(f)
    for f in audit_sync_state(entry, source_dir):
        report.findings.append(f)
    return report


def run_full_audit(slug: str | None = None) -> list[SeriesAuditReport]:
    """Audit one or all series."""
    db = SeriesDatabase()
    db.load()
    reports: list[SeriesAuditReport] = []
    slugs = [slug] if slug else list(db)
    for s in slugs:
        entry = db.get(s)
        if entry is None:
            console.print(f"[red]Not found: {s}[/red]")
            continue
        reports.append(audit_series(entry))
    return reports


def print_reports(reports: list[SeriesAuditReport], category_filter: str | None = None) -> None:
    """Print audit results as a table."""
    rows: list[tuple[str, str, str, str, str]] = []
    for r in reports:
        for f in r.findings:
            if category_filter and f.category != category_filter:
                continue
            rows.append((f.severity, f.category, f.series, f.message, f.detail))

    if not rows:
        scope = f" ({category_filter})" if category_filter else ""
        console.print(f"[green]All series clean{scope}.[/green]")
        # Still report what was scanned
        for r in reports:
            relevant = [f for f in r.findings if not category_filter or f.category == category_filter]
            if not relevant:
                console.print(f"  [dim]{r.series}: ok[/dim]")
        return

    table = Table(title=f"Series Audit ({len(rows)} finding{'s' if len(rows) != 1 else ''})")
    table.add_column("Severity", style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Series")
    table.add_column("Finding")
    table.add_column("Detail", style="dim")

    severity_style = {"error": "red", "warn": "yellow", "info": "blue"}
    for sev, cat, ser, msg, det in rows:
        table.add_row(
            f"[{severity_style.get(sev, 'white')}]{sev}[/]",
            cat, ser, msg, det,
        )
    console.print(table)

    # Summary
    errors = sum(1 for s, *_ in rows if s == "error")
    warnings = sum(1 for s, *_ in rows if s == "warn")
    info = sum(1 for s, *_ in rows if s == "info")
    parts = []
    if errors:
        parts.append(f"[red]{errors} error{'s' if errors != 1 else ''}[/red]")
    if warnings:
        parts.append(f"[yellow]{warnings} warning{'s' if warnings != 1 else ''}[/yellow]")
    if info:
        parts.append(f"[blue]{info} info[/blue]")
    if parts:
        console.print(" · ".join(parts))
