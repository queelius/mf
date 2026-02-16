"""CLI commands for content-to-project linking."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

if TYPE_CHECKING:
    from mf.content.auditor import AuditIssue, AuditStats, ExtendedAuditResult
    from mf.content.matcher import Match

console = Console()


@click.group(name="content")
def content() -> None:
    """Link Hugo content to projects.

    Match content to projects using the linked_project taxonomy.
    """
    pass


@content.command(name="match-projects")
@click.option("-t", "--threshold", type=float, default=0.7, help="Confidence threshold (0.0-1.0)")
@click.option("--type", "content_types", multiple=True, help="Content types to scan (default: post, papers)")
@click.option("-y", "--yes", is_flag=True, help="Apply all matches without confirmation")
@click.option("--project", help="Only match for a specific project")
@click.pass_obj
def match_projects(
    ctx,
    threshold: float,
    content_types: tuple[str, ...],
    yes: bool,
    project: str | None,
) -> None:
    """Match content to projects and update front matter.

    Scans content for mentions of projects and offers to add
    the projects taxonomy to matching content.

    \b
    Examples:
        mf content match-projects
        mf content match-projects --threshold 0.8
        mf content match-projects --project ctk
        mf content match-projects --yes  # Auto-apply all
    """
    from mf.content.frontmatter import add_projects_to_content
    from mf.content.matcher import ProjectMatcher

    dry_run = ctx.dry_run if ctx else False
    matcher = ProjectMatcher()

    if not content_types:
        content_types = ("post", "papers")

    console.print(f"[cyan]Scanning content types: {', '.join(content_types)}[/cyan]")
    console.print(f"[cyan]Confidence threshold: {threshold}[/cyan]")
    console.print()

    if project:
        # Match for a specific project
        matches = matcher.find_matches_for_project(
            project,
            content_types=list(content_types),
            threshold=threshold,
        )

        if not matches:
            console.print(f"[yellow]No matches found for project: {project}[/yellow]")
            return

        console.print(f"[green]Found {len(matches)} potential match(es) for {project}:[/green]")

        for match in matches:
            _display_match(match)

            if yes or Confirm.ask("Add this project to content?", default=True):
                success = add_projects_to_content(
                    match.content_item.path,
                    [match.project_slug],
                    dry_run=dry_run,
                )
                if success:
                    console.print(f"  [green]✓ Added '{match.project_slug}' to {match.content_item.path.name}[/green]")
                else:
                    console.print(f"  [red]✗ Failed to update {match.content_item.path.name}[/red]")
            else:
                console.print("  [dim]Skipped[/dim]")

    else:
        # Find all matches
        suggestions = matcher.suggest_matches(
            threshold=threshold,
            content_types=list(content_types),
        )

        if not suggestions:
            console.print("[yellow]No new matches found.[/yellow]")
            console.print("[dim]All content either has projects set or no matches above threshold.[/dim]")
            return

        console.print(f"[green]Found {len(suggestions)} content item(s) with potential project matches:[/green]")
        console.print()

        total_updated = 0
        total_skipped = 0

        for item, matches in suggestions:
            console.print(f"[bold]{item.title}[/bold]")
            console.print(f"  [dim]{item.path}[/dim]")
            console.print(f"  [dim]Type: {item.content_type}[/dim]")
            console.print()

            for match in matches:
                _display_match(match, indent=2)

                if yes or Confirm.ask("  Add this project?", default=True):
                    success = add_projects_to_content(
                        match.content_item.path,
                        [match.project_slug],
                        dry_run=dry_run,
                    )
                    if success:
                        console.print(f"    [green]✓ Added '{match.project_slug}'[/green]")
                        total_updated += 1
                    else:
                        console.print("    [red]✗ Failed[/red]")
                else:
                    console.print("    [dim]Skipped[/dim]")
                    total_skipped += 1

            console.print()

        console.print()
        console.print(f"[green]Updated: {total_updated}[/green]")
        if total_skipped:
            console.print(f"[yellow]Skipped: {total_skipped}[/yellow]")


def _display_match(match: Match, indent: int = 0) -> None:
    """Display a match result."""
    prefix = " " * indent
    conf_color = "green" if match.confidence >= 0.8 else "yellow" if match.confidence >= 0.6 else "red"

    console.print(f"{prefix}[cyan]→ {match.project_slug}[/cyan] [{conf_color}]{match.confidence:.0%}[/{conf_color}]")
    console.print(f"{prefix}  [dim]{match.match_type.value}: {match.evidence}[/dim]")


@content.command(name="about")
@click.argument("project_slug")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def about_project(project_slug: str, as_json: bool) -> None:
    """Find all content about a specific project.

    \b
    Examples:
        mf content about ctk
        mf content about algebraic-mle --json
    """
    import json as json_module

    from mf.content.scanner import ContentScanner

    scanner = ContentScanner()
    results = scanner.find_content_about_project(project_slug)

    if as_json:
        output = [
            {
                "slug": item.slug,
                "title": item.title,
                "type": item.content_type,
                "path": str(item.path),
                "hugo_path": item.hugo_path,
            }
            for item in results
        ]
        click.echo(json_module.dumps(output, indent=2))
        return

    if not results:
        console.print(f"[yellow]No content found about project: {project_slug}[/yellow]")
        return

    console.print(f"[green]Content about '{project_slug}':[/green]")
    console.print()

    by_type: dict[str, list] = {}
    for item in results:
        by_type.setdefault(item.content_type, []).append(item)

    for content_type, items in sorted(by_type.items()):
        console.print(f"[cyan]{content_type}[/cyan] ({len(items)})")
        for item in items:
            console.print(f"  • {item.title}")
            console.print(f"    [dim]{item.hugo_path}[/dim]")
        console.print()


@content.command(name="list-projects")
@click.option("--with-content", is_flag=True, help="Only show projects that have related content")
def list_projects_with_content(with_content: bool) -> None:
    """List all projects and their content associations.

    Shows how many content items are associated with each project
    through the projects taxonomy.
    """
    from mf.content.matcher import ProjectMatcher
    from mf.content.scanner import ContentScanner

    scanner = ContentScanner()
    matcher = ProjectMatcher()

    # Get all content
    items = scanner.scan_all(include_drafts=False)

    # Count content per project
    project_counts: dict[str, int] = {}
    for item in items:
        for proj in item.projects:
            project_counts[proj] = project_counts.get(proj, 0) + 1

    # Get all projects
    all_projects = matcher.get_project_slugs()

    table = Table(title="Projects and Content")
    table.add_column("Project", style="cyan")
    table.add_column("Content Count", style="green")
    table.add_column("Title")

    for slug in sorted(all_projects):
        count = project_counts.get(slug, 0)

        if with_content and count == 0:
            continue

        project = matcher.get_project(slug)
        title = project["title"] if project else slug

        table.add_row(
            slug,
            str(count) if count else "-",
            title[:40] + "..." if len(title) > 40 else title,
        )

    console.print(table)


@content.command(name="audit")
@click.option(
    "-t",
    "--type",
    "content_types",
    multiple=True,
    help="Content types to audit (default: post, papers, writing)",
)
@click.option(
    "--include-drafts",
    is_flag=True,
    help="Include draft content in audit",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Remove broken linked_project entries",
)
@click.option(
    "-n",
    "--dry-run",
    is_flag=True,
    help="Preview fixes without making changes",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Show detailed information",
)
@click.option(
    "--summary-only",
    is_flag=True,
    help="Only show statistics",
)
@click.option(
    "--check",
    "check_names",
    help="Comma-separated list of checks to run (e.g., required_fields,date_format)",
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default=None,
    help="Minimum severity level to report",
)
@click.option(
    "--list-checks",
    is_flag=True,
    help="List available audit checks and exit",
)
@click.option(
    "--extended",
    is_flag=True,
    help="Run extended audit checks (required_fields, date_format, etc.)",
)
def audit_content(
    content_types: tuple[str, ...],
    include_drafts: bool,
    fix: bool,
    dry_run: bool,
    as_json: bool,
    verbose: bool,
    summary_only: bool,
    check_names: str | None,
    severity: str | None,
    list_checks: bool,
    extended: bool,
) -> None:
    """Audit linked_project references in content.

    Validates that all linked_project entries reference existing projects.
    Reports broken links, hidden project links, and invalid format issues.

    Use --extended to run pluggable content checks (required fields, date format, etc.).

    \b
    Examples:
        mf content audit                    # Full audit
        mf content audit --type post        # Only audit posts
        mf content audit --fix --dry-run    # Preview fixes
        mf content audit --fix              # Apply fixes
        mf content audit --json             # Machine-readable output
        mf content audit --summary-only     # Quick stats only
        mf content audit --list-checks      # Show available checks
        mf content audit --extended         # Run extended checks
        mf content audit --check required_fields,stale_drafts
        mf content audit --severity warning # Min severity level
    """
    from mf.content.auditor import ContentAuditor

    # Handle --list-checks
    if list_checks:
        from mf.content.audit_checks import list_checks as get_checks

        checks = get_checks()
        table = Table(title="Available Audit Checks")
        table.add_column("Name", style="cyan")
        table.add_column("Severity", style="yellow")
        table.add_column("Description")

        for check in checks:
            table.add_row(check["name"], check["severity"], check["description"])

        console.print(table)
        return

    auditor = ContentAuditor()

    if not content_types:
        content_types = auditor.DEFAULT_CONTENT_TYPES

    # If running extended checks or specific checks
    if extended or check_names:
        parsed_checks = check_names.split(",") if check_names else None

        ext_result = auditor.run_checks(
            content_types=content_types,
            include_drafts=include_drafts,
            check_names=parsed_checks,
            min_severity=severity,
        )

        if as_json:
            console.print(ext_result.to_json())
            return

        _display_extended_audit_result(ext_result, verbose, summary_only)
        return

    # Run standard audit
    result = auditor.audit(
        content_types=content_types,
        include_drafts=include_drafts,
    )

    # JSON output
    if as_json:
        console.print(result.to_json())
        return

    # Display summary
    if not summary_only:
        console.print()

    _display_audit_stats(result.stats, verbose)

    if summary_only:
        return

    # Display issues
    errors = result.errors()
    warnings = result.warnings()

    if errors:
        console.print()
        console.print(f"[red]Errors ({len(errors)}):[/red]")
        _display_audit_issues(errors, verbose)

    if warnings and verbose:
        console.print()
        console.print(f"[yellow]Warnings ({len(warnings)}):[/yellow]")
        _display_audit_issues(warnings, verbose)
    elif warnings and not verbose:
        console.print()
        console.print(f"[yellow]Warnings: {len(warnings)} (use --verbose to see details)[/yellow]")

    # Fix mode
    if fix:
        fixable = [i for i in result.issues if i.issue_type.value == "missing_project"]
        if not fixable:
            console.print()
            console.print("[green]No fixable issues found.[/green]")
            return

        console.print()
        if dry_run:
            console.print(f"[cyan]Would fix {len(fixable)} broken link(s):[/cyan]")
        else:
            console.print(f"[cyan]Fixing {len(fixable)} broken link(s):[/cyan]")

        fixed, failed = auditor.fix_issues(fixable, dry_run=dry_run)

        console.print()
        if dry_run:
            console.print(f"[dim]Dry run: {fixed} issue(s) would be fixed[/dim]")
        else:
            console.print(f"[green]Fixed: {fixed}[/green]")
            if failed:
                console.print(f"[red]Failed: {failed}[/red]")

    # Summary status
    console.print()
    if result.has_errors:
        console.print("[red]Audit found errors. Run with --fix to remove broken links.[/red]")
    elif result.has_warnings:
        console.print("[yellow]Audit passed with warnings.[/yellow]")
    else:
        console.print("[green]Audit passed. All linked_project references are valid.[/green]")


def _display_audit_stats(stats: AuditStats, verbose: bool) -> None:
    """Display audit statistics in a table."""
    from rich.table import Table

    table = Table(title="Audit Summary", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Content audited:", str(stats.content_audited))
    table.add_row("With project links:", str(stats.with_project_links))
    table.add_row("Without links:", str(stats.without_links))
    table.add_row("", "")
    table.add_row("Valid links:", f"[green]{stats.valid_links}[/green]")

    if stats.broken_links > 0:
        table.add_row("Broken links:", f"[red]{stats.broken_links}[/red]")
    else:
        table.add_row("Broken links:", "0")

    if stats.hidden_project_links > 0:
        table.add_row("Hidden project links:", f"[yellow]{stats.hidden_project_links}[/yellow]")

    if stats.invalid_format_links > 0:
        table.add_row("Invalid format links:", f"[yellow]{stats.invalid_format_links}[/yellow]")

    if verbose:
        table.add_row("", "")
        table.add_row("Projects total:", str(stats.projects_total))
        table.add_row("Projects with content:", str(stats.projects_with_content))
        table.add_row("Projects without:", str(stats.projects_without_content))

    console.print(table)


def _display_audit_issues(issues: list[AuditIssue], verbose: bool) -> None:
    """Display audit issues."""
    for issue in issues:
        console.print(f"  [bold]• {issue.title}[/bold]")
        console.print(f"    [dim]{issue.path}[/dim]")
        console.print(f"    {issue.message}")
        if verbose:
            console.print(f"    [dim]Type: {issue.issue_type.value}[/dim]")
        console.print()


def _display_extended_audit_result(result: ExtendedAuditResult, verbose: bool, summary_only: bool) -> None:
    """Display extended audit result."""

    # Summary table
    table = Table(title="Extended Audit Summary", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Content checked:", str(result.content_checked))
    table.add_row("Content with issues:", str(result.content_with_issues))
    table.add_row("Total issues:", str(len(result.issues)))

    # By severity
    by_sev = result._group_by_severity()
    if by_sev.get("error", 0):
        table.add_row("Errors:", f"[red]{by_sev['error']}[/red]")
    if by_sev.get("warning", 0):
        table.add_row("Warnings:", f"[yellow]{by_sev['warning']}[/yellow]")
    if by_sev.get("info", 0):
        table.add_row("Info:", f"[blue]{by_sev['info']}[/blue]")

    console.print()
    console.print(table)

    if summary_only:
        return

    # By check type
    by_check = result._group_by_check()
    if by_check and verbose:
        console.print()
        check_table = Table(title="Issues by Check")
        check_table.add_column("Check", style="cyan")
        check_table.add_column("Count", style="white")
        for check_name, count in sorted(by_check.items()):
            check_table.add_row(check_name, str(count))
        console.print(check_table)

    # Display issues
    errors = result.errors()
    warnings = result.warnings()
    infos = result.infos()

    if errors:
        console.print()
        console.print(f"[red]Errors ({len(errors)}):[/red]")
        for issue in errors:
            console.print(f"  [bold]• {issue.title}[/bold] [{issue.check_name}]")
            console.print(f"    [dim]{issue.path}[/dim]")
            console.print(f"    {issue.message}")
            if verbose and issue.field_name:
                console.print(f"    [dim]Field: {issue.field_name}[/dim]")
            console.print()

    if warnings:
        console.print()
        console.print(f"[yellow]Warnings ({len(warnings)}):[/yellow]")
        if verbose:
            for issue in warnings:
                console.print(f"  [bold]• {issue.title}[/bold] [{issue.check_name}]")
                console.print(f"    [dim]{issue.path}[/dim]")
                console.print(f"    {issue.message}")
                console.print()
        else:
            console.print("  [dim]Use --verbose to see details[/dim]")

    if infos and verbose:
        console.print()
        console.print(f"[blue]Info ({len(infos)}):[/blue]")
        for issue in infos:
            console.print(f"  [bold]• {issue.title}[/bold] [{issue.check_name}]")
            console.print(f"    [dim]{issue.path}[/dim]")
            console.print(f"    {issue.message}")
            console.print()

    # Summary status
    console.print()
    if result.has_errors:
        console.print("[red]Extended audit found errors.[/red]")
    elif result.has_warnings:
        console.print("[yellow]Extended audit passed with warnings.[/yellow]")
    else:
        console.print("[green]Extended audit passed. No issues found.[/green]")
