"""
Paper staleness detection.

Check if source files have changed since last ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from mf.core.crypto import verify_file_hash
from mf.core.database import PaperDatabase, PaperEntry

console = Console()


@dataclass
class SyncStatus:
    """Status of papers after checking for staleness."""

    stale: list[tuple[PaperEntry, Path, str]]  # (entry, source_path, reason)
    missing: list[tuple[PaperEntry, str]]  # (entry, source_path_str)
    up_to_date: list[tuple[PaperEntry, Path]]
    skipped: list[tuple[PaperEntry, str]]  # (entry, reason)


def check_paper_staleness(entry: PaperEntry) -> tuple[str, Path | None]:
    """Check if a paper's source has changed.

    Args:
        entry: Paper database entry

    Returns:
        Tuple of (status, source_path) where status is one of:
        - "up_to_date": Source unchanged
        - "stale": Source has changed
        - "no_hash": No hash stored (assume stale)
        - "missing": Source file not found
        - "skipped": No source path or source is a directory
    """
    source_path = entry.source_path
    if not source_path:
        return ("skipped", None)

    if not source_path.exists():
        return ("missing", source_path)

    if source_path.is_dir():
        return ("skipped", source_path)

    stored_hash = entry.source_hash
    if not stored_hash:
        return ("no_hash", source_path)

    if verify_file_hash(source_path, stored_hash):
        return ("up_to_date", source_path)
    else:
        return ("stale", source_path)


def check_all_papers(db: PaperDatabase) -> SyncStatus:
    """Check all papers for staleness.

    Args:
        db: Paper database (must be loaded)

    Returns:
        SyncStatus with categorized papers
    """
    status = SyncStatus(stale=[], missing=[], up_to_date=[], skipped=[])

    for entry in db.papers_with_source():
        result, path = check_paper_staleness(entry)

        if result == "up_to_date" and path is not None:
            status.up_to_date.append((entry, path))
        elif result == "stale" and path is not None:
            status.stale.append((entry, path, "changed"))
        elif result == "no_hash" and path is not None:
            status.stale.append((entry, path, "no hash"))
        elif result == "missing":
            status.missing.append((entry, str(entry.source_path)))
        elif result == "skipped":
            status.skipped.append((entry, "directory reference"))

    return status


def print_sync_status(status: SyncStatus) -> None:
    """Print sync status summary."""
    console.print()
    console.print("=" * 60)
    console.print(f"[green]Up to date:[/green]  {len(status.up_to_date)}")
    console.print(f"[yellow]Stale:[/yellow]       {len(status.stale)}")
    console.print(f"[blue]Skipped:[/blue]     {len(status.skipped)}")
    console.print(f"[red]Missing:[/red]     {len(status.missing)}")
    console.print("=" * 60)

    if status.up_to_date:
        console.print("\n[green]Up-to-date papers:[/green]")
        for entry, _ in status.up_to_date:
            console.print(f"  ✓ {entry.slug}")

    if status.skipped:
        console.print("\n[blue]Skipped (directory references):[/blue]")
        for entry, _reason in status.skipped:
            console.print(f"  ⊘ {entry.slug}")

    if status.missing:
        console.print("\n[red]Missing source files:[/red]")
        for entry, path in status.missing:
            console.print(f"  ✗ {entry.slug}")
            console.print(f"    Source: {path}")

    if status.stale:
        console.print("\n[yellow]Stale papers:[/yellow]")
        for entry, stale_path, reason in status.stale:
            console.print(f"  • {entry.slug} ({reason})")
            console.print(f"    Source: {stale_path}")


def paper_status(slug: str | None = None) -> None:
    """Report paper staleness status.

    Args:
        slug: If provided, check only this paper
    """
    db = PaperDatabase()
    db.load()

    if slug:
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Paper not found: {slug}[/red]")
            return

        result, source_path = check_paper_staleness(entry)
        if result == "missing":
            console.print(f"[red]Source file missing: {entry.source_path}[/red]")
        elif result == "skipped":
            console.print(f"[yellow]{slug}: skipped (no trackable source)[/yellow]")
        elif result == "up_to_date":
            console.print(f"[green]{slug}: up to date[/green]")
        elif result in ("stale", "no_hash"):
            console.print(f"[yellow]{slug}: stale ({result})[/yellow]")
        return

    console.print(f"Checking {len(db)} papers for changes...")
    status = check_all_papers(db)
    print_sync_status(status)
