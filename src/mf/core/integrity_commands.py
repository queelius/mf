"""CLI commands for database integrity checking."""

import json as json_module

import click
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

console = Console()


@click.group(name="integrity")
def integrity() -> None:
    """Database integrity checking and repair.

    Validates consistency across paper_db, projects_db, projects_cache, and series_db.
    """
    pass


@integrity.command(name="check")
@click.option("--db", "db_name", help="Check specific database (paper_db, projects_db, projects_cache, series_db)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed information")
def integrity_check(
    db_name: str | None,
    as_json: bool,
    verbose: bool,
) -> None:
    """Run integrity checks on databases.

    Validates cross-database consistency, orphaned entries, and invalid references.

    \b
    Examples:
        mf integrity check                 # Full check
        mf integrity check --db paper_db   # Check specific database
        mf integrity check --json          # JSON output
    """
    from mf.core.integrity import IntegrityChecker

    checker = IntegrityChecker()

    result = checker.check_database(db_name) if db_name else checker.check_all()

    if as_json:
        console.print(result.to_json())
        return

    # Summary table
    table = Table(title="Integrity Check Results", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    for db, count in sorted(result.checked.items()):
        table.add_row(f"{db} entries checked:", str(count))

    table.add_row("", "")
    table.add_row("Total issues:", str(len(result.issues)))

    by_sev = result._group_by_severity()
    if by_sev.get("error"):
        table.add_row("Errors:", f"[red]{by_sev['error']}[/red]")
    if by_sev.get("warning"):
        table.add_row("Warnings:", f"[yellow]{by_sev['warning']}[/yellow]")
    if by_sev.get("info"):
        table.add_row("Info:", f"[blue]{by_sev['info']}[/blue]")

    fixable_count = len(result.fixable_issues())
    if fixable_count:
        table.add_row("Fixable issues:", f"[green]{fixable_count}[/green]")

    console.print()
    console.print(table)

    if not result.issues:
        console.print()
        console.print("[green]All integrity checks passed![/green]")
        return

    # Issues by database
    by_db = result._group_by_database()
    if by_db and verbose:
        console.print()
        db_table = Table(title="Issues by Database")
        db_table.add_column("Database", style="cyan")
        db_table.add_column("Count", style="white")
        for db, count in sorted(by_db.items()):
            db_table.add_row(db, str(count))
        console.print(db_table)

    # Display issues
    errors = result.errors()
    if errors:
        console.print()
        console.print(f"[red]Errors ({len(errors)}):[/red]")
        for issue in errors:
            console.print(f"  [bold]• [{issue.database}] {issue.entry_id}[/bold]")
            console.print(f"    {issue.message}")
            if verbose and issue.extra:
                for key, value in issue.extra.items():
                    console.print(f"    [dim]{key}: {value}[/dim]")

    other_issues = [i for i in result.issues if i.severity.value != "error"]
    if other_issues and verbose:
        console.print()
        console.print(f"[yellow]Other Issues ({len(other_issues)}):[/yellow]")
        for issue in other_issues:
            sev_color = "yellow" if issue.severity.value == "warning" else "blue"
            fixable_marker = " [green](fixable)[/green]" if issue.fixable else ""
            console.print(
                f"  [{sev_color}]• [{issue.database}] {issue.entry_id}[/{sev_color}]{fixable_marker}"
            )
            console.print(f"    {issue.message}")
    elif other_issues and not verbose:
        console.print()
        console.print(f"[dim]{len(other_issues)} other issues (use --verbose to see)[/dim]")

    # Summary
    console.print()
    if result.has_errors:
        console.print("[red]Integrity check found errors.[/red]")
    elif result.issues:
        console.print("[yellow]Integrity check passed with warnings/info.[/yellow]")

    if result.has_fixable:
        console.print("[dim]Run 'mf integrity fix' to fix auto-fixable issues.[/dim]")


@integrity.command(name="fix")
@click.option("--db", "db_name", help="Fix specific database only")
@click.option("-n", "--dry-run", is_flag=True, help="Preview fixes without making changes")
@click.option("-y", "--yes", is_flag=True, help="Apply fixes without confirmation")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def integrity_fix(
    db_name: str | None,
    dry_run: bool,
    yes: bool,
    as_json: bool,
) -> None:
    """Fix auto-fixable integrity issues.

    Currently fixes:
    - Stale cache entries (removes orphaned cache entries)
    - Sync state orphans (clears sync state for non-existent posts)

    \b
    Examples:
        mf integrity fix --dry-run    # Preview fixes
        mf integrity fix -y           # Apply fixes without confirmation
        mf integrity fix --db projects_cache  # Fix specific database
    """
    from mf.core.integrity import IntegrityChecker

    checker = IntegrityChecker()

    result = checker.check_database(db_name) if db_name else checker.check_all()

    fixable = result.fixable_issues()

    if not fixable:
        if as_json:
            console.print(json_module.dumps({"fixed": 0, "failed": 0}))
        else:
            console.print("[green]No fixable issues found.[/green]")
        return

    if as_json:
        # In JSON mode, just report what would be fixed
        output = {
            "fixable": [i.to_dict() for i in fixable],
            "count": len(fixable),
        }
        console.print(json_module.dumps(output, indent=2))
        return

    console.print(f"[cyan]Found {len(fixable)} fixable issue(s):[/cyan]")
    console.print()

    for issue in fixable:
        console.print(f"  • [{issue.database}] {issue.entry_id}")
        console.print(f"    {issue.message}")

    console.print()

    if dry_run:
        console.print("[dim]Dry run mode - previewing fixes:[/dim]")
        fixed, failed = checker.fix_issues(fixable, dry_run=True)
        console.print()
        console.print(f"[dim]Would fix {fixed} issue(s)[/dim]")
        return

    if not yes and not Confirm.ask(f"Apply {len(fixable)} fix(es)?", default=False):
        console.print("[dim]Aborted.[/dim]")
        return

    fixed, failed = checker.fix_issues(fixable, dry_run=False)

    console.print()
    console.print(f"[green]Fixed: {fixed}[/green]")
    if failed:
        console.print(f"[red]Failed: {failed}[/red]")


@integrity.command(name="orphans")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed information")
def integrity_orphans(
    as_json: bool,
    verbose: bool,
) -> None:
    """Find orphaned entries across databases.

    Shows entries that exist in databases but have no corresponding content files.

    \b
    Examples:
        mf integrity orphans           # Find orphans
        mf integrity orphans --json    # JSON output
    """
    from mf.core.integrity import IntegrityChecker

    checker = IntegrityChecker()
    result = checker.find_orphans()

    if as_json:
        console.print(result.to_json())
        return

    if not result.issues:
        console.print("[green]No orphaned entries found![/green]")
        return

    table = Table(title="Orphaned Entries")
    table.add_column("Database", style="cyan")
    table.add_column("Entry", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Fixable", style="green")

    for issue in result.issues:
        table.add_row(
            issue.database,
            issue.entry_id,
            issue.issue_type.value,
            "Yes" if issue.fixable else "No",
        )

    console.print(table)

    if verbose:
        console.print()
        for issue in result.issues:
            console.print(f"[bold]{issue.entry_id}[/bold] ({issue.database})")
            console.print(f"  {issue.message}")
            if issue.extra:
                for key, value in issue.extra.items():
                    console.print(f"  [dim]{key}: {value}[/dim]")

    fixable_count = len([i for i in result.issues if i.fixable])
    if fixable_count:
        console.print()
        console.print(f"[dim]{fixable_count} orphan(s) can be auto-fixed with 'mf integrity fix'[/dim]")
