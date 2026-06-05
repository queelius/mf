"""Aggregate render drift across all projection modules (read-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mf.core.drift import RenderFinding, check_render_drift

if TYPE_CHECKING:
    from rich.console import Console


def collect_status() -> list[tuple[str, list[RenderFinding]]]:
    """Run check_render_drift for every projection module.

    Robust: a module that fails to load or render yields a single synthetic
    'error' finding rather than crashing the whole status run.
    """
    from mf.packages.generator import make_renderer as packages_renderer
    from mf.papers.generator import make_renderer as papers_renderer
    from mf.projects.generator import make_renderer as projects_renderer
    from mf.publications.generate import make_renderer as pubs_renderer

    entries = [
        ("publications", pubs_renderer),
        ("packages", packages_renderer),
        ("papers", papers_renderer),
        ("projects", projects_renderer),
    ]
    results: list[tuple[str, list[RenderFinding]]] = []
    for section, factory in entries:
        try:
            findings = check_render_drift(factory())
        except Exception as exc:  # noqa: BLE001 - status must survive one module failing
            findings = [RenderFinding(slug="(module)", status="error", detail=str(exc))]
        results.append((section, findings))
    return results


def _counts(findings: list[RenderFinding]) -> dict[str, int]:
    counts = {"current": 0, "stale": 0, "missing": 0, "orphan": 0, "error": 0}
    for f in findings:
        counts[f.status] = counts.get(f.status, 0) + 1
    return counts


def print_status(
    results: list[tuple[str, list[RenderFinding]]],
    *,
    console: Console,
    verbose: bool = False,
) -> None:
    """Print the drift dashboard. Read-only."""
    from rich.table import Table

    from mf.core.drift import STATUS_STYLE

    table = Table(title="Render drift across modules")
    table.add_column("Module", style="cyan")
    table.add_column("Current", justify="right", style="dim")
    table.add_column("Stale", justify="right")
    table.add_column("Missing", justify="right")
    table.add_column("Orphan", justify="right")
    table.add_column("Drift", justify="right", style="bold")

    totals = {"current": 0, "stale": 0, "missing": 0, "orphan": 0, "error": 0}
    for section, findings in results:
        c = _counts(findings)
        for k in totals:
            totals[k] += c[k]
        drift = c["stale"] + c["missing"] + c["orphan"] + c["error"]
        errored = c["error"] > 0
        label = f"{section} (error)" if errored else section
        table.add_row(
            label,
            str(c["current"]),
            str(c["stale"]),
            str(c["missing"]),
            str(c["orphan"]),
            str(drift),
        )

    grand_drift = totals["stale"] + totals["missing"] + totals["orphan"] + totals["error"]
    table.add_row(
        "TOTAL",
        str(totals["current"]),
        str(totals["stale"]),
        str(totals["missing"]),
        str(totals["orphan"]),
        str(grand_drift),
        style="bold",
    )
    console.print(table)

    if verbose:
        for section, findings in results:
            drifted = [f for f in findings if f.status != "current"]
            if not drifted:
                continue
            console.print(f"\n[bold cyan]{section}[/bold cyan]")
            for f in sorted(drifted, key=lambda x: (x.status, x.slug)):
                style = STATUS_STYLE.get(f.status, "")
                tag = f"[{style}]{f.status}[/{style}]" if style else f.status
                line = f"  {tag}  {f.slug}"
                if f.detail:
                    line += f"  [dim]{f.detail}[/dim]"
                console.print(line)

    if grand_drift == 0:
        console.print("\n[green]All projection pages are current.[/green]")
    else:
        console.print(
            "\n[dim]Run 'mf <module> diff' for detail, or "
            "'mf <module> generate' to reconcile.[/dim]"
        )
