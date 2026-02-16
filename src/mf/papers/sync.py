"""
Paper synchronization and staleness detection.

Check if source .tex files have changed and regenerate papers as needed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from mf.core.crypto import verify_file_hash
from mf.core.database import PaperDatabase, PaperEntry
from mf.core.prompts import confirm

console = Console()

# Default timeout in seconds (5 minutes)
DEFAULT_TIMEOUT = 300


@dataclass
class SyncStatus:
    """Status of papers after checking for staleness."""

    stale: list[tuple[PaperEntry, Path, str]]  # (entry, source_path, reason)
    missing: list[tuple[PaperEntry, str]]  # (entry, source_path_str)
    up_to_date: list[tuple[PaperEntry, Path]]
    skipped: list[tuple[PaperEntry, str]]  # (entry, reason)


@dataclass
class ProcessingResult:
    """Result of processing a single paper."""

    slug: str
    success: bool
    error: str | None = None
    duration: float = 0.0


@dataclass
class SyncResults:
    """Results of sync operation."""

    succeeded: list[ProcessingResult] = field(default_factory=list)
    failed: list[ProcessingResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    def print_summary(self) -> None:
        """Print a summary of results."""
        if self.succeeded:
            console.print(f"\n[green]✓ Succeeded ({len(self.succeeded)}):[/green]")
            for r in self.succeeded:
                console.print(f"  • {r.slug} ({r.duration:.1f}s)")

        if self.failed:
            console.print(f"\n[red]✗ Failed ({len(self.failed)}):[/red]")
            table = Table(show_header=True, header_style="bold red")
            table.add_column("Paper")
            table.add_column("Error")
            for r in self.failed:
                table.add_row(r.slug, r.error or "Unknown error")
            console.print(table)


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
        - "skipped": Source is a directory (not trackable)
        - "skipped_non_tex": Source format is not tex (docx, pregenerated)
    """
    # Check for non-tex source formats first
    if entry.source_format != "tex":
        return ("skipped_non_tex", entry.source_path)

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
        elif result == "skipped_non_tex":
            status.skipped.append((entry, f"non-tex format ({entry.source_format})"))

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


def sync_papers(
    slug: str | None = None,
    auto_yes: bool = False,
    dry_run: bool = False,
    workers: int = 1,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    """Check for stale papers and optionally regenerate them.

    Args:
        slug: If provided, only sync this specific paper
        auto_yes: Auto-confirm regeneration
        dry_run: Preview only, don't regenerate
        workers: Number of parallel workers for processing (default: 1)
        timeout: Timeout per paper in seconds (default: 300 = 5 minutes)
    """
    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No files will be modified[/yellow]")
        console.print("=" * 60)
        console.print()

    # Load database
    db = PaperDatabase()
    db.load()

    # Single paper mode
    if slug:
        entry = db.get(slug)
        if not entry:
            console.print(f"[red]Paper not found: {slug}[/red]")
            return

        result, source_path = check_paper_staleness(entry)
        if result == "missing":
            console.print(f"[red]Source file missing: {entry.source_path}[/red]")
            return
        if result == "skipped":
            console.print(f"[yellow]Paper {slug} has directory source (cannot sync)[/yellow]")
            return
        if result == "up_to_date":
            console.print(f"[green]Paper {slug} is up to date[/green]")
            return
        if source_path is None:
            console.print(f"[red]No source path for paper {slug}[/red]")
            return

        console.print(f"Paper {slug} is stale ({result})")
        if process_stale_paper(slug, source_path, auto_yes, dry_run, timeout):
            console.print(f"[green]Successfully processed {slug}[/green]")
        return

    console.print(f"Checking {len(db)} papers for changes...")

    # Check staleness
    status = check_all_papers(db)
    print_sync_status(status)

    if not status.stale:
        console.print("\n[green]All papers are up to date![/green]")
        return

    # Process stale papers
    console.print(f"\nFound {len(status.stale)} stale paper(s)")
    console.print(f"[dim]Timeout: {timeout}s per paper[/dim]")

    if not auto_yes and not dry_run and not confirm("Process stale papers?"):
        console.print("Aborted")
        return

    # Use parallel processing if workers > 1
    if workers > 1 and len(status.stale) > 1:
        results = _process_papers_parallel(status.stale, auto_yes, dry_run, workers, timeout)
    else:
        results = _process_papers_sequential(status.stale, auto_yes, dry_run, timeout)

    # Print results summary
    results.print_summary()

    action = "Would process" if dry_run else "Processed"
    console.print(f"\n{action} {results.success_count}/{len(status.stale)} papers successfully")


def _process_papers_sequential(
    stale_papers: list[tuple[PaperEntry, Path, str]],
    auto_yes: bool,
    dry_run: bool,
    timeout: int,
) -> SyncResults:
    """Process stale papers sequentially.

    Args:
        stale_papers: List of (entry, source_path, reason) tuples
        auto_yes: Auto-confirm prompts
        dry_run: Preview only
        timeout: Timeout per paper in seconds

    Returns:
        SyncResults with success/failure details
    """
    results = SyncResults()

    for entry, source_path, _ in stale_papers:
        result = _process_single_paper_with_timeout(
            entry.slug, source_path, auto_yes, dry_run, timeout, verbose=True
        )
        if result.success:
            results.succeeded.append(result)
        else:
            results.failed.append(result)

    return results


def _process_papers_parallel(
    stale_papers: list[tuple[PaperEntry, Path, str]],
    auto_yes: bool,
    dry_run: bool,
    workers: int,
    timeout: int,
) -> SyncResults:
    """Process stale papers in parallel using a thread pool.

    Args:
        stale_papers: List of (entry, source_path, reason) tuples
        auto_yes: Auto-confirm prompts
        dry_run: Preview only
        workers: Number of parallel workers
        timeout: Timeout per paper in seconds

    Returns:
        SyncResults with success/failure details
    """
    results = SyncResults()

    # Limit workers to number of papers
    actual_workers = min(workers, len(stale_papers))
    console.print(f"[cyan]Processing with {actual_workers} parallel workers...[/cyan]")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Processing {len(stale_papers)} papers...",
            total=len(stale_papers),
        )

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    _process_single_paper_with_timeout,
                    entry.slug,
                    source_path,
                    auto_yes,
                    dry_run,
                    timeout,
                    verbose=False,  # Suppress output in parallel mode
                ): entry.slug
                for entry, source_path, _ in stale_papers
            }

            # Collect results as they complete
            for future in as_completed(futures, timeout=timeout * len(stale_papers)):
                slug = futures[future]
                try:
                    result = future.result(timeout=timeout)
                    if result.success:
                        results.succeeded.append(result)
                        status_str = f"[green]✓[/green] {slug} ({result.duration:.1f}s)"
                    else:
                        results.failed.append(result)
                        status_str = f"[red]✗[/red] {slug}: {result.error}"
                except FuturesTimeoutError:
                    result = ProcessingResult(
                        slug=slug,
                        success=False,
                        error=f"Timeout after {timeout}s",
                    )
                    results.failed.append(result)
                    status_str = f"[red]⏱[/red] {slug}: timeout"
                except Exception as e:
                    result = ProcessingResult(
                        slug=slug,
                        success=False,
                        error=str(e),
                    )
                    results.failed.append(result)
                    status_str = f"[red]✗[/red] {slug}: {e}"

                progress.update(task, advance=1, description=status_str)

    return results


def _process_single_paper_with_timeout(
    slug: str,
    source_path: Path,
    auto_yes: bool,
    dry_run: bool,
    timeout: int,
    verbose: bool = True,
) -> ProcessingResult:
    """Process a single paper with timeout tracking.

    Args:
        slug: Paper slug
        source_path: Path to source .tex file
        auto_yes: Auto-confirm prompts
        dry_run: Preview only
        timeout: Timeout in seconds
        verbose: Whether to print progress

    Returns:
        ProcessingResult with success/failure details
    """
    import subprocess
    import sys
    import time

    start_time = time.time()

    if dry_run:
        return ProcessingResult(slug=slug, success=True, duration=0.0)

    if verbose:
        console.print(f"\n[cyan]Processing {slug}...[/cyan]")

    try:
        # Use subprocess with timeout for better process control
        # This allows us to kill stuck tex2any/pdflatex processes
        result = subprocess.run(
            [
                sys.executable, "-c",
                f"""
import sys
sys.path.insert(0, '/home/spinoza/github/repos/metafunctor/scripts/mf/src')
from mf.papers.processor import process_paper
success = process_paper(
    '{source_path}',
    slug='{slug}',
    auto_yes={auto_yes},
    dry_run={dry_run},
)
sys.exit(0 if success else 1)
"""
            ],
            timeout=timeout,
            capture_output=not verbose,
            text=True,
        )

        duration = time.time() - start_time
        success = result.returncode == 0

        if not success and not verbose:
            error = result.stderr[:200] if result.stderr else "Processing failed"
        else:
            error = None

        return ProcessingResult(
            slug=slug,
            success=success,
            error=error,
            duration=duration,
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        if verbose:
            console.print(f"  [red]Timeout after {timeout}s[/red]")
        return ProcessingResult(
            slug=slug,
            success=False,
            error=f"Timeout after {timeout}s",
            duration=duration,
        )
    except Exception as e:
        duration = time.time() - start_time
        if verbose:
            console.print(f"  [red]Error: {e}[/red]")
        return ProcessingResult(
            slug=slug,
            success=False,
            error=str(e),
            duration=duration,
        )


def process_stale_paper(
    slug: str,
    source_path: Path,
    auto_yes: bool = False,
    dry_run: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """Process a single stale paper.

    Args:
        slug: Paper slug
        source_path: Path to source .tex file
        auto_yes: Auto-confirm prompts
        dry_run: Preview only
        timeout: Timeout in seconds

    Returns:
        True if successful
    """
    result = _process_single_paper_with_timeout(
        slug, source_path, auto_yes, dry_run, timeout, verbose=True
    )
    return result.success
