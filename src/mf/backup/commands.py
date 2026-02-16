"""
Backup management CLI commands.

Provides commands for listing, cleaning, and rolling back database backups.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mf.config.commands import get_config_value
from mf.core.backup import (
    DEFAULT_KEEP_COUNT,
    DEFAULT_KEEP_DAYS,
    BackupInfo,
    list_backups,
    rollback_database,
)
from mf.core.config import get_paths

console = Console()


def _get_keep_days() -> int:
    """Get configured keep_days value."""
    return int(get_config_value("backup.keep_days", DEFAULT_KEEP_DAYS))


def _get_keep_count() -> int:
    """Get configured keep_count value."""
    return int(get_config_value("backup.keep_count", DEFAULT_KEEP_COUNT))


# All database names for CLI choices
ALL_DBS = ["paper_db", "projects_db", "series_db"]


def _get_backup_dirs() -> dict[str, Path]:
    """Get all backup directories with their names."""
    paths = get_paths()
    return {
        "paper_db": paths.paper_backups,
        "projects_db": paths.projects_backups,
        "series_db": paths.series_backups,
    }


def _get_db_path(db_name: str) -> Path:
    """Get the database file path for a given database name."""
    paths = get_paths()
    return {
        "paper_db": paths.paper_db,
        "projects_db": paths.projects_db,
        "series_db": paths.series_db,
    }[db_name]


def _format_age(days: float) -> str:
    """Format age in human-readable form."""
    if days < 1:
        hours = days * 24
        if hours < 1:
            return f"{int(hours * 60)}m ago"
        return f"{int(hours)}h ago"
    elif days < 7:
        return f"{int(days)}d ago"
    elif days < 30:
        return f"{int(days / 7)}w ago"
    else:
        return f"{int(days / 30)}mo ago"


@click.group()
def backup():
    """Manage database backups.

    List, clean up, and restore backups of paper_db and projects_db.
    Backups are created automatically when databases are modified.
    """
    pass


@backup.command(name="list")
@click.option(
    "-d", "--db",
    type=click.Choice(ALL_DBS + ["all"]),
    default="all",
    help="Which database backups to list",
)
@click.option(
    "-n", "--limit",
    type=int,
    default=10,
    help="Maximum number of backups to show per database",
)
@click.option("--all", "show_all", is_flag=True, help="Show all backups (no limit)")
def list_cmd(db: str, limit: int, show_all: bool):
    """List available backups.

    Shows backups sorted by date with size and age information.
    """
    backup_dirs = _get_backup_dirs()

    if db != "all":
        backup_dirs = {db: backup_dirs[db]}

    total_count = 0
    total_size = 0

    for db_name, backup_dir in backup_dirs.items():
        backups = list_backups(backup_dir, db_name)

        if not backups:
            console.print(f"[dim]No backups found for {db_name}[/dim]")
            continue

        total_count += len(backups)
        total_size += sum(b.size_bytes for b in backups)

        # Apply limit
        display_backups = backups if show_all else backups[:limit]
        hidden = len(backups) - len(display_backups)

        table = Table(
            title=f"[bold]{db_name}[/bold] ({len(backups)} backups)",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Date", style="green")
        table.add_column("Age", style="yellow", justify="right")
        table.add_column("Size", style="blue", justify="right")
        table.add_column("Filename", style="dim")

        for i, backup in enumerate(display_backups):
            table.add_row(
                str(i),
                backup.timestamp.strftime("%Y-%m-%d %H:%M"),
                _format_age(backup.age_days),
                backup.size_human,
                backup.path.name,
            )

        console.print(table)

        if hidden > 0:
            console.print(f"  [dim]... and {hidden} older backups (use --all to see all)[/dim]")
        console.print()

    # Summary
    if total_count > 0:
        size_mb = total_size / (1024 * 1024)
        console.print(
            f"[dim]Total: {total_count} backups, {size_mb:.1f} MB[/dim]"
        )


@backup.command(name="status")
def status_cmd():
    """Show backup system status and statistics."""
    backup_dirs = _get_backup_dirs()
    keep_days = _get_keep_days()
    keep_count = _get_keep_count()

    # Collect stats
    stats = []
    for db_name, backup_dir in backup_dirs.items():
        backups = list_backups(backup_dir, db_name)
        if backups:
            oldest = min(b.timestamp for b in backups)
            newest = max(b.timestamp for b in backups)
            total_size = sum(b.size_bytes for b in backups)
            over_30_days = sum(1 for b in backups if b.age_days > keep_days)

            stats.append({
                "db": db_name,
                "count": len(backups),
                "size": total_size,
                "oldest": oldest,
                "newest": newest,
                "over_30": over_30_days,
            })
        else:
            stats.append({
                "db": db_name,
                "count": 0,
                "size": 0,
                "oldest": None,
                "newest": None,
                "over_30": 0,
            })

    # Display
    table = Table(title="Backup Status", show_header=True, header_style="bold cyan")
    table.add_column("Database")
    table.add_column("Count", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Latest", justify="right")
    table.add_column("Oldest", justify="right")
    table.add_column(f">{keep_days}d", justify="right", style="yellow")

    for s in stats:
        table.add_row(
            s["db"],
            str(s["count"]),
            f"{s['size'] / 1024:.1f} KB" if s["size"] else "-",
            s["newest"].strftime("%Y-%m-%d") if s["newest"] else "-",
            s["oldest"].strftime("%Y-%m-%d") if s["oldest"] else "-",
            str(s["over_30"]) if s["over_30"] > 0 else "[green]0[/green]",
        )

    console.print(table)

    # Retention settings
    console.print()
    console.print(Panel(
        f"[bold]Retention Policy[/bold]\n"
        f"Keep minimum: [cyan]{keep_count}[/cyan] backups\n"
        f"Delete older than: [cyan]{keep_days}[/cyan] days\n\n"
        f"[dim]Backups are cleaned automatically when databases are saved.[/dim]\n"
        f"[dim]Use 'mf config set backup.keep_days N' to change retention.[/dim]",
        title="Settings",
    ))


@backup.command(name="clean")
@click.option(
    "-d", "--db",
    type=click.Choice(ALL_DBS + ["all"]),
    default="all",
    help="Which database backups to clean",
)
@click.option(
    "--days",
    type=int,
    default=None,
    help="Remove backups older than this many days (default: from config)",
)
@click.option(
    "--keep",
    type=int,
    default=None,
    help="Always keep at least this many backups (default: from config)",
)
@click.option("--dry-run", "-n", is_flag=True, help="Preview what would be deleted")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def clean_cmd(db: str, days: int | None, keep: int | None, dry_run: bool, force: bool):
    """Clean up old backups.

    Removes backups older than --days while always keeping at least --keep
    backups per database. Uses values from config if not specified.

    Examples:
        mf backup clean                    # Use configured defaults
        mf backup clean --days 7           # Delete backups older than 7 days
        mf backup clean --db paper_db      # Only clean paper_db backups
        mf backup clean -n                 # Preview what would be deleted
    """
    # Use configured values if not specified
    if days is None:
        days = _get_keep_days()
    if keep is None:
        keep = _get_keep_count()

    backup_dirs = _get_backup_dirs()

    if db != "all":
        backup_dirs = {db: backup_dirs[db]}

    # Find what would be deleted
    to_delete: list[tuple[str, BackupInfo]] = []
    for db_name, backup_dir in backup_dirs.items():
        backups = list_backups(backup_dir, db_name)

        # Keep the first 'keep' backups regardless of age
        for i, backup in enumerate(backups):
            if i < keep:
                continue
            if backup.age_days > days:
                to_delete.append((db_name, backup))

    if not to_delete:
        console.print("[green]No old backups to clean up.[/green]")
        return

    # Show what will be deleted
    console.print(f"[bold]Found {len(to_delete)} backup(s) to delete:[/bold]")
    for _db_name, backup in to_delete[:10]:
        console.print(
            f"  [red]x[/red] {backup.path.name} "
            f"[dim]({_format_age(backup.age_days)}, {backup.size_human})[/dim]"
        )
    if len(to_delete) > 10:
        console.print(f"  [dim]... and {len(to_delete) - 10} more[/dim]")

    total_size = sum(b.size_bytes for _, b in to_delete)
    console.print(f"\nTotal: [bold]{len(to_delete)}[/bold] files, [bold]{total_size / 1024:.1f} KB[/bold]")

    if dry_run:
        console.print("\n[yellow]DRY RUN - no files deleted[/yellow]")
        return

    # Confirm
    if not force and not click.confirm("\nProceed with deletion?"):
        console.print("[yellow]Cancelled[/yellow]")
        return

    # Delete
    deleted = 0
    for _db_name, backup in to_delete:
        try:
            backup.path.unlink(missing_ok=True)
            deleted += 1
        except OSError as e:
            console.print(f"[red]Failed to delete {backup.path.name}: {e}[/red]")

    console.print(f"\n[green]Deleted {deleted} backup(s)[/green]")


@backup.command(name="rollback")
@click.argument("database", type=click.Choice(ALL_DBS))
@click.option(
    "-i", "--index",
    type=int,
    default=0,
    help="Backup index to restore (0 = most recent, 1 = second most recent, etc.)",
)
@click.option("--dry-run", "-n", is_flag=True, help="Preview without making changes")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def rollback_cmd(database: str, index: int, dry_run: bool, force: bool):
    """Restore a database from backup.

    Creates a backup of the current state before restoring.

    Examples:
        mf backup rollback paper_db              # Restore most recent backup
        mf backup rollback paper_db -i 1         # Restore second most recent
        mf backup rollback paper_db -n           # Preview (dry run)
    """
    backup_dirs = _get_backup_dirs()
    backup_dir = backup_dirs[database]

    # Get the backup to restore
    backups = list_backups(backup_dir, database)
    if not backups:
        console.print(f"[red]No backups found for {database}[/red]")
        return

    if index >= len(backups):
        console.print(f"[red]Backup index {index} out of range (only {len(backups)} backups)[/red]")
        return

    backup = backups[index]

    # Get current database path
    db_path = _get_db_path(database)

    # Show what will happen
    console.print(Panel(
        f"[bold]Database:[/bold] {database}\n"
        f"[bold]Current:[/bold] {db_path.name}\n"
        f"[bold]Restore from:[/bold] {backup.path.name}\n"
        f"[bold]Backup date:[/bold] {backup.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"[bold]Backup age:[/bold] {_format_age(backup.age_days)}\n"
        f"[bold]Backup size:[/bold] {backup.size_human}",
        title="Rollback Preview",
    ))

    if dry_run:
        console.print("\n[yellow]DRY RUN - no changes made[/yellow]")
        return

    if not force:
        console.print("\n[yellow]Warning: This will create a backup of the current state, then restore.[/yellow]")
        if not click.confirm("Proceed with rollback?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    try:
        rollback_database(db_path, backup_dir, index)
        console.print(f"\n[green]Successfully restored {database} from {backup.path.name}[/green]")
        console.print("[dim]A backup of the previous state was created.[/dim]")
    except Exception as e:
        console.print(f"[red]Rollback failed: {e}[/red]")
        raise click.Abort() from e
