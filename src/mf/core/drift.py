"""Render-drift engine: compare on-disk Hugo pages against a fresh render.

A projection module (papers, projects, packages, publications) supplies a
Renderer binding; this module supplies the mechanism. Drift is computed live
by re-rendering and comparing semantically (frontmatter dict equality plus
body equality), never by textual YAML comparison and never by persisted hash
state.

This mirrors the binding-plus-mechanism seam in mf.core.field_ops.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mf.core.frontmatter import parse_post, parse_text

if TYPE_CHECKING:
    from rich.console import Console


@runtime_checkable
class Renderer(Protocol):
    """Per-module binding the drift engine needs to inspect one section."""

    section: str

    def iter_slugs(self) -> Iterable[str]:
        """Slugs that generate would produce a primary page for."""
        ...

    def existing_slugs(self) -> Iterable[str]:
        """Slugs that currently have a primary page on disk."""
        ...

    def hugo_path(self, slug: str) -> Path:
        """Path to the primary page for slug (may or may not exist)."""
        ...

    def render_page(self, slug: str) -> str | None:
        """Text generate would write for slug, or None if not renderable."""
        ...


@dataclass
class RenderFinding:
    """One page's drift status. status in {current, stale, missing, orphan}."""

    slug: str
    status: str
    detail: str = ""


STATUS_STYLE = {
    "stale": "yellow",
    "missing": "green",
    "orphan": "red",
    "current": "dim",
    "error": "red",
}

_DRY_RUN_VERB = {
    "missing": "create",
    "stale": "update",
    "current": "skip",
    "orphan": "skip (orphan)",
}


def _semantic_equal(rendered: str, path: Path) -> bool:
    r_fm, r_body = parse_text(rendered)
    d_fm, d_body = parse_post(path)
    return r_fm == d_fm and r_body == d_body


def check_render_drift(renderer: Renderer) -> list[RenderFinding]:
    """Compare every page against a fresh render. Read-only."""
    findings: list[RenderFinding] = []
    known = set(renderer.iter_slugs())
    on_disk = set(renderer.existing_slugs())

    # A known slug whose render_page returns None and which has no on-disk
    # page emits no finding: nothing to generate and nothing on disk is not drift.
    for slug in sorted(known):
        path = renderer.hugo_path(slug)
        rendered = renderer.render_page(slug)
        if rendered is None:
            if slug in on_disk or path.exists():
                findings.append(RenderFinding(slug, "orphan", "on disk but not renderable"))
            continue
        if not path.exists():
            findings.append(RenderFinding(slug, "missing", "generate would create"))
        elif _semantic_equal(rendered, path):
            findings.append(RenderFinding(slug, "current"))
        else:
            findings.append(RenderFinding(slug, "stale", "generate would update"))

    for slug in sorted(on_disk - known):
        findings.append(RenderFinding(slug, "orphan", "on disk, unknown to database"))

    return findings


def print_drift_report(
    findings: list[RenderFinding],
    *,
    section: str,
    console: Console,
    show_current: bool = False,
) -> None:
    """Print a findings table. Drift-only by default."""
    from rich.table import Table

    relevant = findings if show_current else [f for f in findings if f.status != "current"]
    if not relevant:
        console.print(f"[green]{section}: all pages current ({len(findings)} checked)[/green]")
        return

    table = Table(title=f"Render drift: {section}")
    table.add_column("Slug", style="cyan")
    table.add_column("Status")
    table.add_column("Detail", style="dim")
    for f in sorted(relevant, key=lambda x: (x.status, x.slug)):
        style = STATUS_STYLE.get(f.status, "")
        status_cell = f"[{style}]{f.status}[/{style}]" if style else f.status
        table.add_row(f.slug, status_cell, f.detail)
    console.print(table)


def print_render_diff(renderer: Renderer, slug: str, console: Console) -> None:
    """Print a unified diff for one page: minus is on disk, plus is generate."""
    from rich.panel import Panel
    from rich.syntax import Syntax

    rendered = renderer.render_page(slug)
    if rendered is None:
        console.print(f"[dim]{slug}: not renderable; nothing to diff[/dim]")
        return
    path = renderer.hugo_path(slug)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    diff_lines = list(
        difflib.unified_diff(
            current.splitlines(),
            rendered.splitlines(),
            fromfile=f"{slug} (on disk)",
            tofile=f"{slug} (generate)",
            lineterm="",
        )
    )
    if not diff_lines:
        console.print(f"[dim]{slug}: no textual difference[/dim]")
        return
    syntax = Syntax("\n".join(diff_lines), "diff", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"diff: {slug}", border_style="cyan"))


def print_dry_run_preview(
    renderer: Renderer,
    *,
    console: Console,
    only_slug: str | None = None,
) -> None:
    """Print 'would create|update|skip: path' for each page."""
    findings = check_render_drift(renderer)
    if only_slug is not None:
        findings = [f for f in findings if f.slug == only_slug]
        if not findings:
            console.print(f"[yellow]No matching slug in {renderer.section}: {only_slug}[/yellow]")
            return
    for f in sorted(findings, key=lambda x: x.slug):
        verb = _DRY_RUN_VERB.get(f.status, f.status)
        console.print(f"  would {verb}: {renderer.hugo_path(f.slug)}")


def run_diff_command(
    renderer: Renderer,
    *,
    console: Console,
    slug: str | None = None,
    full: bool = False,
) -> None:
    """Shared body of every `mf <module> diff` command. Read-only."""
    findings = check_render_drift(renderer)
    if slug is not None:
        match = next((f for f in findings if f.slug == slug), None)
        if match is None:
            console.print(f"[red]Unknown slug for {renderer.section}: {slug}[/red]")
            raise SystemExit(1)
        print_drift_report([match], section=renderer.section, console=console, show_current=True)
        if match.status in ("stale", "missing"):
            print_render_diff(renderer, slug, console)
        return
    print_drift_report(findings, section=renderer.section, console=console)
    if full:
        for f in findings:
            if f.status in ("stale", "missing"):
                print_render_diff(renderer, f.slug, console)
